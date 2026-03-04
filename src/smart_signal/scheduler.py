"""Simple 5-minute scheduler for the collector."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from smart_signal.binance_symbols import DEFAULT_SYMBOL_LIST_PATH
from smart_signal.collector import DEFAULT_CONCURRENCY, DEFAULT_PROFILE_DIR, DEFAULT_RESPONSE_TIMEOUT_S, DEFAULT_RETRIES, run_collector_async
from smart_signal.db import DEFAULT_DB_PATH
from smart_signal.logging_utils import DEFAULT_LOG_BACKUP_COUNT, DEFAULT_LOG_DIR, configure_logging, install_exception_logging
from smart_signal.price_stream import DEFAULT_FLUSH_SECONDS, DEFAULT_PRICE_SNAPSHOT_PATH, run_price_stream
from smart_signal.web import create_server


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DashboardHandle:
    host: str
    port: int
    server: object
    thread: threading.Thread


def seconds_until_next_interval(interval_seconds: int, now_ts: float | None = None) -> float:
    current = time.time() if now_ts is None else now_ts
    remainder = current % interval_seconds
    if remainder == 0:
        return 0.0
    return interval_seconds - remainder


def build_collector_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        db_path=args.db_path,
        profile_dir=args.profile_dir,
        symbol_list_path=args.symbol_list_path,
        symbols=args.symbols,
        refresh_symbols=args.refresh_symbols,
        stage1_only=args.stage1_only,
        headless=args.headless,
        concurrency=args.concurrency,
        retries=args.retries,
        response_timeout=args.response_timeout,
        log_level=args.log_level,
        log_dir=args.log_dir,
        log_filename="collector.log",
        log_backup_count=args.log_backup_count,
    )


def start_dashboard(args: argparse.Namespace) -> DashboardHandle:
    server = create_server(
        host=args.dashboard_host,
        port=args.dashboard_port,
        db_path=Path(args.db_path),
        price_snapshot_path=Path(args.price_snapshot_path),
    )
    thread = threading.Thread(target=server.serve_forever, name="smart-signal-dashboard", daemon=True)
    thread.start()
    LOGGER.info("dashboard serving on http://%s:%s", args.dashboard_host, args.dashboard_port)
    return DashboardHandle(host=args.dashboard_host, port=args.dashboard_port, server=server, thread=thread)


def stop_dashboard(handle: DashboardHandle | None) -> None:
    if handle is None:
        return
    handle.server.shutdown()
    handle.server.server_close()
    handle.thread.join(timeout=3)


async def run_scheduled_loop(args: argparse.Namespace, stop_event: threading.Event | None = None) -> int:
    collector_args = build_collector_args(args)
    iteration = 0
    price_stop_event = asyncio.Event()
    price_task: asyncio.Task[int] | None = None

    if args.with_price_stream:
        price_task = asyncio.create_task(
            run_price_stream(
                snapshot_path=args.price_snapshot_path,
                flush_seconds=args.price_stream_flush_seconds,
                stop_event=price_stop_event,
            ),
            name="smart-signal-price-stream",
        )

    try:
        while True:
            if stop_event and stop_event.is_set():
                LOGGER.info("stop requested before next collection run")
                return 0
            if price_task is not None and price_task.done():
                result = price_task.result()
                LOGGER.warning("price stream task exited with code=%s", result)
                price_task = None

            if iteration == 0 and not args.align_to_interval:
                LOGGER.info("starting initial collection immediately")
            else:
                wait_seconds = seconds_until_next_interval(args.interval_seconds)
                if wait_seconds > 0:
                    next_run = datetime.now(UTC).timestamp() + wait_seconds
                    LOGGER.info(
                        "sleeping %.2fs until next run at %s",
                        wait_seconds,
                        datetime.fromtimestamp(next_run, tz=UTC).isoformat().replace("+00:00", "Z"),
                    )
                    await _sleep_with_stop(wait_seconds, stop_event)

            started_at = time.perf_counter()
            LOGGER.info("collector run %s started", iteration + 1)
            try:
                exit_code = await run_collector_async(collector_args)
            except Exception:
                LOGGER.exception("collector run %s crashed", iteration + 1)
                exit_code = 1
            elapsed = time.perf_counter() - started_at
            LOGGER.info("collector run %s finished with exit_code=%s in %.2fs", iteration + 1, exit_code, elapsed)
            iteration += 1

            if args.run_once:
                return exit_code
    finally:
        if price_task is not None:
            price_stop_event.set()
            await asyncio.gather(price_task, return_exceptions=True)


async def _sleep_with_stop(seconds: float, stop_event: threading.Event | None) -> None:
    if stop_event is None:
        await asyncio.sleep(seconds)
        return

    deadline = time.monotonic() + seconds
    while not stop_event.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        await asyncio.sleep(min(remaining, 1.0))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Smart Signal collector on a recurring interval.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR), help="Persistent Playwright profile directory.")
    parser.add_argument("--symbol-list-path", default=str(DEFAULT_SYMBOL_LIST_PATH), help="Static full-market symbol list file.")
    parser.add_argument("--symbols", default="", help="Comma-separated explicit symbol allowlist.")
    parser.add_argument("--refresh-symbols", action="store_true", help="Force refresh Binance exchangeInfo before collection starts.")
    parser.add_argument(
        "--stage1-only",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Restrict collection to BTCUSDT and ETHUSDT validation mode.",
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True, help="Run browser headless.")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Number of symbols to collect concurrently.")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retry count per symbol after the first attempt.")
    parser.add_argument("--response-timeout", type=float, default=DEFAULT_RESPONSE_TIMEOUT_S, help="Seconds to wait for each network operation.")
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Collection interval in seconds.")
    parser.add_argument("--run-once", action="store_true", help="Run one collection cycle and exit.")
    parser.add_argument(
        "--align-to-interval",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Align collection starts to wall-clock interval boundaries.",
    )
    parser.add_argument(
        "--with-dashboard",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Serve the dashboard alongside the scheduler.",
    )
    parser.add_argument(
        "--with-price-stream",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run Binance Futures websocket ticker stream alongside the scheduler.",
    )
    parser.add_argument("--dashboard-host", default="127.0.0.1", help="Dashboard bind host.")
    parser.add_argument("--dashboard-port", type=int, default=8765, help="Dashboard bind port.")
    parser.add_argument("--price-snapshot-path", default=str(DEFAULT_PRICE_SNAPSHOT_PATH), help="JSON file path for the latest websocket price snapshot.")
    parser.add_argument("--price-stream-flush-seconds", type=float, default=DEFAULT_FLUSH_SECONDS, help="Flush interval for the websocket price snapshot.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for rotating log files.")
    parser.add_argument("--log-filename", default="scheduler.log", help="Scheduler log filename.")
    parser.add_argument("--log-backup-count", type=int, default=DEFAULT_LOG_BACKUP_COUNT, help="Number of rotated log files to keep.")
    return parser.parse_args()


def main() -> None:
    try:
        args = parse_args()
        logfile = configure_logging(
            log_level=args.log_level,
            log_dir=args.log_dir,
            log_filename=args.log_filename,
            backup_count=args.log_backup_count,
        )
        install_exception_logging(__name__)
        LOGGER.info("logging to %s", logfile)

        stop_event = threading.Event()
        dashboard_handle: DashboardHandle | None = None

        def _request_stop(*_: object) -> None:
            LOGGER.info("shutdown signal received")
            stop_event.set()

        with suppress(ValueError):
            signal.signal(signal.SIGINT, _request_stop)
            signal.signal(signal.SIGTERM, _request_stop)

        try:
            if args.with_dashboard:
                dashboard_handle = start_dashboard(args)
            raise SystemExit(asyncio.run(run_scheduled_loop(args, stop_event=stop_event)))
        finally:
            stop_dashboard(dashboard_handle)
    except KeyboardInterrupt:
        raise
    except Exception:
        LOGGER.exception("scheduler entrypoint crashed")
        raise


if __name__ == "__main__":
    main()
