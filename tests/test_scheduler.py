from __future__ import annotations

from argparse import Namespace

from smart_signal.scheduler import build_collector_args, seconds_until_next_interval


def test_seconds_until_next_interval_aligns_to_boundary() -> None:
    assert seconds_until_next_interval(300, now_ts=600.0) == 0.0
    assert seconds_until_next_interval(300, now_ts=601.0) == 299.0
    assert seconds_until_next_interval(300, now_ts=899.5) == 0.5


def test_build_collector_args_maps_scheduler_flags() -> None:
    scheduler_args = Namespace(
        db_path="data/test.sqlite3",
        profile_dir="pw-profile",
        symbol_list_path="config/binance_usdt_perpetual_symbols.txt",
        symbols="BTCUSDT",
        refresh_symbols=False,
        stage1_only=True,
        headless=False,
        concurrency=5,
        retries=1,
        response_timeout=12.5,
        log_level="DEBUG",
        log_dir="logs",
        log_backup_count=7,
    )

    collector_args = build_collector_args(scheduler_args)

    assert collector_args.db_path == "data/test.sqlite3"
    assert collector_args.profile_dir == "pw-profile"
    assert collector_args.symbol_list_path == "config/binance_usdt_perpetual_symbols.txt"
    assert collector_args.symbols == "BTCUSDT"
    assert collector_args.refresh_symbols is False
    assert collector_args.stage1_only is True
    assert collector_args.headless is False
    assert collector_args.concurrency == 5
    assert collector_args.retries == 1
    assert collector_args.response_timeout == 12.5
    assert collector_args.log_level == "DEBUG"
    assert collector_args.log_dir == "logs"
    assert collector_args.log_filename == "collector.log"
    assert collector_args.log_backup_count == 7
