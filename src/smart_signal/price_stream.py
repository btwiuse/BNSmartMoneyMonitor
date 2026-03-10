"""Binance Futures ticker websocket stream."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from smart_signal.logging_utils import DEFAULT_LOG_BACKUP_COUNT, DEFAULT_LOG_DIR, configure_logging, install_exception_logging
from smart_signal.parser import normalize_number


LOGGER = logging.getLogger(__name__)

DEFAULT_PRICE_SNAPSHOT_PATH = Path("data") / "futures_price_snapshot.json"
DEFAULT_WS_URL = "wss://fstream.binance.com/ws/!ticker@arr"
DEFAULT_FLUSH_SECONDS = 2.0
DEFAULT_RECONNECT_SECONDS = 23 * 60 * 60


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_price_snapshot(snapshot_path: str | Path = DEFAULT_PRICE_SNAPSHOT_PATH) -> dict[str, Any]:
    path = Path(snapshot_path)
    if not path.exists():
        return {
            "as_of": None,
            "source": DEFAULT_WS_URL,
            "symbol_count": 0,
            "prices": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("price snapshot payload must be a JSON object")
    prices = payload.get("prices")
    if not isinstance(prices, dict):
        payload["prices"] = {}
    payload.setdefault("as_of", None)
    payload.setdefault("source", DEFAULT_WS_URL)
    payload["symbol_count"] = len(payload["prices"])
    return payload


def save_price_snapshot(prices: dict[str, dict[str, Any]], snapshot_path: str | Path = DEFAULT_PRICE_SNAPSHOT_PATH) -> Path:
    path = Path(snapshot_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": utc_now_iso(),
        "source": DEFAULT_WS_URL,
        "symbol_count": len(prices),
        "prices": prices,
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return path


def price_snapshot_rows(ts_utc: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    prices = payload.get("prices") or {}
    rows: list[dict[str, Any]] = []
    for symbol, row in prices.items():
        if not isinstance(symbol, str) or not isinstance(row, dict):
            continue
        rows.append(
            {
                "ts_utc": ts_utc,
                "symbol": symbol.upper(),
                "last_price": normalize_number(row.get("last_price")),
                "event_time_ms": row.get("event_time_ms"),
                "raw_json": row,
            }
        )
    return rows


def _extract_ticker_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def apply_ticker_updates(prices: dict[str, dict[str, Any]], payload: Any) -> int:
    updated = 0
    for row in _extract_ticker_rows(payload):
        symbol = row.get("s")
        last_price = normalize_number(row.get("c"))
        if not isinstance(symbol, str) or last_price is None:
            continue
        prices[symbol.upper()] = {
            "last_price": last_price,
            "event_time_ms": row.get("E"),
        }
        updated += 1
    return updated


async def run_price_stream(
    *,
    snapshot_path: str | Path = DEFAULT_PRICE_SNAPSHOT_PATH,
    flush_seconds: float = DEFAULT_FLUSH_SECONDS,
    reconnect_after_seconds: float = DEFAULT_RECONNECT_SECONDS,
    stop_event: asyncio.Event | None = None,
) -> int:
    snapshot = load_price_snapshot(snapshot_path)
    prices: dict[str, dict[str, Any]] = dict(snapshot.get("prices") or {})

    while True:
        if stop_event and stop_event.is_set():
            save_price_snapshot(prices, snapshot_path)
            LOGGER.info("price stream stop requested before connect")
            return 0

        try:
            try:
                import websockets
            except ModuleNotFoundError:
                LOGGER.error("websockets package is not installed; run pip install -r requirements.txt")
                return 1

            async with websockets.connect(
                DEFAULT_WS_URL,
                ping_interval=150,
                ping_timeout=600,
                max_queue=1024,
            ) as websocket:
                LOGGER.info("connected to price stream %s", DEFAULT_WS_URL)
                started_at = time.monotonic()
                last_flush_at = 0.0

                while True:
                    if stop_event and stop_event.is_set():
                        save_price_snapshot(prices, snapshot_path)
                        LOGGER.info("price stream stop requested")
                        return 0
                    if time.monotonic() - started_at >= reconnect_after_seconds:
                        LOGGER.info("price stream reconnecting before 24h session limit")
                        break

                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        if time.monotonic() - last_flush_at >= flush_seconds:
                            save_price_snapshot(prices, snapshot_path)
                            last_flush_at = time.monotonic()
                        continue

                    payload = json.loads(message)
                    updated = apply_ticker_updates(prices, payload)
                    if updated and time.monotonic() - last_flush_at >= flush_seconds:
                        save_price_snapshot(prices, snapshot_path)
                        last_flush_at = time.monotonic()
        except asyncio.CancelledError:
            save_price_snapshot(prices, snapshot_path)
            raise
        except Exception:
            LOGGER.exception("price stream disconnected; retrying in 5s")
            await asyncio.sleep(5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Binance Futures all-market ticker websocket stream.")
    parser.add_argument("--snapshot-path", default=str(DEFAULT_PRICE_SNAPSHOT_PATH), help="JSON file path for the latest price snapshot.")
    parser.add_argument("--flush-seconds", type=float, default=DEFAULT_FLUSH_SECONDS, help="Write snapshot file at most once per this many seconds.")
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for rotating log files.")
    parser.add_argument("--log-filename", default="price_stream.log", help="Price stream log filename.")
    parser.add_argument("--log-backup-count", type=int, default=DEFAULT_LOG_BACKUP_COUNT, help="Number of rotated log files to keep.")
    return parser.parse_args()


def main() -> None:
    try:
        args = parse_args()
        configure_logging(
            log_level=args.log_level,
            log_dir=args.log_dir,
            log_filename=args.log_filename,
            backup_count=args.log_backup_count,
        )
        install_exception_logging(__name__)
        raise SystemExit(
            asyncio.run(
                run_price_stream(
                    snapshot_path=args.snapshot_path,
                    flush_seconds=args.flush_seconds,
                )
            )
        )
    except KeyboardInterrupt:
        raise
    except Exception:
        LOGGER.exception("price stream entrypoint crashed")
        raise


if __name__ == "__main__":
    main()
