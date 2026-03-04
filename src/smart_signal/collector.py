"""Binance Smart Signal collector entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Error, Page, Playwright, TimeoutError, async_playwright

from smart_signal.binance_symbols import DEFAULT_STAGE1_SYMBOLS, DEFAULT_SYMBOL_LIST_PATH, SymbolFetchError, SymbolUniverse, get_target_symbols
from smart_signal.db import DEFAULT_DB_PATH, fetch_distinct_symbols, floor_utc_to_5m, init_db, save_snapshots
from smart_signal.logging_utils import DEFAULT_LOG_BACKUP_COUNT, DEFAULT_LOG_DIR, configure_logging, install_exception_logging
from smart_signal.parser import ParsedSignal, parse_overview_payload


LOGGER = logging.getLogger(__name__)

DEFAULT_PROFILE_DIR = Path("pw-profile")
DEFAULT_TIME_RANGE = "30m"
DEFAULT_SIDE = "BOTH"
DEFAULT_SORT_BY = "TIME"
DEFAULT_SORT_ORDER = "DESC"
DEFAULT_PAGE = 1
DEFAULT_CONCURRENCY = 3
DEFAULT_RETRIES = 2
DEFAULT_RESPONSE_TIMEOUT_S = 20.0
DEFAULT_NAVIGATION_TIMEOUT_MS = 60_000
@dataclass(slots=True)
class CapturedPayload:
    symbol: str
    cohort: str
    raw_json: str
    parsed: ParsedSignal | None
    error: str | None = None


@dataclass(slots=True)
class SymbolRunResult:
    symbol: str
    captures: list[CapturedPayload] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_signal_url(
    symbol: str,
    *,
    time_range: str = DEFAULT_TIME_RANGE,
    side: str = DEFAULT_SIDE,
    sort_by: str = DEFAULT_SORT_BY,
    sort_order: str = DEFAULT_SORT_ORDER,
    page: int = DEFAULT_PAGE,
) -> str:
    return (
        f"https://www.binance.com/zh-CN/smart-money/signal/{symbol.upper()}"
        f"?timeRange={time_range}&side={side}&sortBy={sort_by}&sortOrder={sort_order}&page={page}"
    )


def payload_contains_signal_fields(payload: Any) -> bool:
    if isinstance(payload, dict):
        normalized_keys = {str(key).replace("-", "").replace("_", "").lower() for key in payload}
        if {
            "longtradersqty",
            "shorttradersqty",
            "longwhalesqty",
            "shortwhalesqty",
            "avgentryprice",
            "positionusd",
            "positionusdt",
        } & normalized_keys:
            return True
        return any(payload_contains_signal_fields(value) for value in payload.values())
    if isinstance(payload, list):
        return any(payload_contains_signal_fields(item) for item in payload)
    return False


def payload_to_raw_json(payload: Any, *, metadata: dict[str, Any] | None = None) -> str:
    if metadata:
        return json.dumps({"metadata": metadata, "payload": payload}, ensure_ascii=True, sort_keys=True)
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def captures_to_rows(ts_utc: str, capture: CapturedPayload, symbol: str) -> list[dict[str, Any]]:
    if capture.parsed is None:
        return [
            {
                "ts_utc": ts_utc,
                "symbol": symbol,
                "cohort": capture.cohort,
                "side": side,
                "position_qty": None,
                "position_usdt": None,
                "avg_entry_price": None,
                "raw_json": capture.raw_json,
            }
            for side in ("long", "short")
        ]
    return capture.parsed.as_rows(ts_utc=ts_utc, symbol=symbol, cohort=capture.cohort, raw_json=capture.raw_json)


async def create_context(playwright: Playwright, profile_dir: Path, *, headless: bool) -> BrowserContext:
    profile_dir.mkdir(parents=True, exist_ok=True)
    return await playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        viewport={"width": 1440, "height": 960},
    )


async def collect_symbol(
    context: BrowserContext,
    symbol: str,
    *,
    response_timeout_s: float = DEFAULT_RESPONSE_TIMEOUT_S,
) -> SymbolRunResult:
    result = SymbolRunResult(symbol=symbol)
    page = await context.new_page()
    page.set_default_navigation_timeout(DEFAULT_NAVIGATION_TIMEOUT_MS)
    page.set_default_timeout(DEFAULT_NAVIGATION_TIMEOUT_MS)

    try:
        await page.goto(build_signal_url(symbol), wait_until="domcontentloaded")
        for cohort in ("trader", "whale"):
            try:
                capture = await collect_cohort(page, symbol, cohort, response_timeout_s=response_timeout_s)
                result.captures.append(capture)
            except Exception as exc:
                message = f"{cohort} capture failed: {exc}"
                LOGGER.exception("symbol=%s cohort=%s capture failed", symbol, cohort)
                result.errors.append(message)
                result.captures.append(
                    CapturedPayload(
                        symbol=symbol,
                        cohort=cohort,
                        raw_json=payload_to_raw_json(
                            {"symbol": symbol, "cohort": cohort},
                            metadata={"error": message, "url": page.url},
                        ),
                        parsed=None,
                        error=message,
                    )
                )
    finally:
        await page.close()

    return result


async def collect_cohort(
    page: Page,
    symbol: str,
    cohort: str,
    *,
    response_timeout_s: float,
) -> CapturedPayload:
    payload = await fetch_overview_payload(page, symbol, timeout_s=response_timeout_s)
    raw_json = payload_to_raw_json(
        payload,
        metadata={
            "url": build_overview_api_url(symbol),
            "cohort": cohort,
        },
    )
    parsed = parse_overview_payload(payload, cohort=cohort)
    if parsed is None:
        return CapturedPayload(symbol=symbol, cohort=cohort, raw_json=raw_json, parsed=None, error="overview payload parse failed")
    return CapturedPayload(symbol=symbol, cohort=cohort, raw_json=raw_json, parsed=parsed)


def build_overview_api_url(symbol: str) -> str:
    return f"https://www.binance.com/bapi/futures/v1/public/future/smart-money/signal/overview?symbol={symbol.upper()}"


async def fetch_overview_payload(page: Page, symbol: str, *, timeout_s: float) -> dict[str, Any]:
    script = """
        async ({ url }) => {
            const response = await window.fetch(url, { credentials: 'include' });
            return await response.json();
        }
    """
    payload = await asyncio.wait_for(
        page.evaluate(script, {"url": build_overview_api_url(symbol)}),
        timeout=timeout_s,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("overview response was not a JSON object")
    return payload


async def run_collector_async(args: argparse.Namespace) -> int:
    configure_logging(
        log_level=args.log_level,
        log_dir=args.log_dir,
        log_filename=args.log_filename,
        backup_count=args.log_backup_count,
    )
    install_exception_logging(__name__)

    init_db(args.db_path)
    ts_utc = floor_utc_to_5m()
    allowlist = [symbol.strip().upper() for symbol in args.symbols.split(",")] if args.symbols else None
    try:
        universe = get_target_symbols(
            stage1_only=args.stage1_only,
            allowlist=allowlist,
            list_path=args.symbol_list_path,
            refresh=args.refresh_symbols,
        )
    except SymbolFetchError:
        if allowlist:
            LOGGER.exception("unable to resolve target symbols and no broader fallback is available")
            return 1
        cached_symbols = fetch_distinct_symbols(args.db_path)
        if args.stage1_only:
            cached_symbols = [symbol for symbol in cached_symbols if symbol in DEFAULT_STAGE1_SYMBOLS]
        if not cached_symbols:
            LOGGER.exception("unable to resolve target symbols from Binance, local cache, or existing database")
            return 1
        LOGGER.warning("falling back to %s symbols discovered from existing SQLite snapshots", len(cached_symbols))
        universe = SymbolUniverse(symbols=sorted(cached_symbols), source_url=f"sqlite:{args.db_path}")
    if not universe.symbols:
        LOGGER.error("no target symbols resolved")
        return 1

    async with async_playwright() as playwright:
        context = await create_context(playwright, Path(args.profile_dir), headless=args.headless)
        try:
            semaphore = asyncio.Semaphore(args.concurrency)
            tasks = [
                _collect_with_retries(
                    context,
                    symbol,
                    retries=args.retries,
                    semaphore=semaphore,
                    response_timeout_s=args.response_timeout,
                )
                for symbol in universe.symbols
            ]
            results = await asyncio.gather(*tasks)
        finally:
            await context.close()

    rows: list[dict[str, Any]] = []
    failed_symbols: list[str] = []
    for result in results:
        if result.errors:
            failed_symbols.append(result.symbol)
        for capture in result.captures:
            rows.extend(captures_to_rows(ts_utc, capture, result.symbol))

    save_snapshots(rows, db_path=args.db_path)
    LOGGER.info("saved %s snapshot rows for %s symbols into %s", len(rows), len(results), args.db_path)
    if failed_symbols:
        LOGGER.warning("symbols with capture errors: %s", ",".join(failed_symbols))
    return 0


async def _collect_with_retries(
    context: BrowserContext,
    symbol: str,
    *,
    retries: int,
    semaphore: asyncio.Semaphore,
    response_timeout_s: float,
) -> SymbolRunResult:
    async with semaphore:
        last_result: SymbolRunResult | None = None
        for attempt in range(1, retries + 2):
            try:
                result = await collect_symbol(
                    context,
                    symbol,
                    response_timeout_s=response_timeout_s,
                )
                if not result.errors:
                    return result
                last_result = result
                LOGGER.warning("symbol=%s completed with errors on attempt %s", symbol, attempt)
            except (TimeoutError, Error, asyncio.TimeoutError) as exc:
                LOGGER.warning("symbol=%s attempt=%s failed: %s", symbol, attempt, exc)
                last_result = SymbolRunResult(symbol=symbol, errors=[str(exc)])
            if attempt <= retries:
                await asyncio.sleep(min(2 * attempt, 5))

        return last_result or SymbolRunResult(symbol=symbol, errors=["unknown collector failure"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Binance Smart Signal data into SQLite.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR), help="Persistent Playwright profile directory.")
    parser.add_argument("--symbol-list-path", default=str(DEFAULT_SYMBOL_LIST_PATH), help="Static full-market symbol list file.")
    parser.add_argument("--symbols", default="", help="Comma-separated explicit symbol allowlist.")
    parser.add_argument(
        "--refresh-symbols",
        action="store_true",
        help="Force refresh Binance exchangeInfo instead of using the local cache.",
    )
    parser.add_argument(
        "--stage1-only",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=f"Restrict collection to initial validation symbols: {', '.join(DEFAULT_STAGE1_SYMBOLS)}.",
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True, help="Run browser headless.")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Number of symbols to collect concurrently.")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retry count per symbol after the first attempt.")
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=DEFAULT_RESPONSE_TIMEOUT_S,
        help="Seconds to wait for a Smart Signal API response after opening or switching tabs.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for rotating log files.")
    parser.add_argument("--log-filename", default="collector.log", help="Collector log filename.")
    parser.add_argument("--log-backup-count", type=int, default=DEFAULT_LOG_BACKUP_COUNT, help="Number of rotated log files to keep.")
    return parser.parse_args()


def main() -> None:
    try:
        args = parse_args()
        raise SystemExit(asyncio.run(run_collector_async(args)))
    except KeyboardInterrupt:
        raise
    except Exception:
        LOGGER.exception("collector entrypoint crashed")
        raise


if __name__ == "__main__":
    main()
