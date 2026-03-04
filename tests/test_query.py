from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from smart_signal.db import fetch_symbol_timeseries, init_db, save_snapshots
from smart_signal.query import format_table
from smart_signal.query import run_query


def _seed(db_path: Path) -> None:
    init_db(db_path)
    save_snapshots(
        [
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "trader",
                "side": "long",
                "position_qty": 10.0,
                "position_usdt": 10.0,
                "avg_entry_price": 20.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "trader",
                "side": "short",
                "position_qty": 11.0,
                "position_usdt": 11.0,
                "avg_entry_price": 21.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "whale",
                "side": "long",
                "position_qty": 12.0,
                "position_usdt": 12.0,
                "avg_entry_price": 22.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "whale",
                "side": "short",
                "position_qty": 13.0,
                "position_usdt": 13.0,
                "avg_entry_price": 23.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:05:00Z",
                "symbol": "BTCUSDT",
                "cohort": "trader",
                "side": "long",
                "position_qty": 20.0,
                "position_usdt": 20.0,
                "avg_entry_price": 30.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:05:00Z",
                "symbol": "BTCUSDT",
                "cohort": "trader",
                "side": "short",
                "position_qty": 10.0,
                "position_usdt": 10.0,
                "avg_entry_price": 31.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:05:00Z",
                "symbol": "BTCUSDT",
                "cohort": "whale",
                "side": "long",
                "position_qty": 24.0,
                "position_usdt": 24.0,
                "avg_entry_price": 32.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:05:00Z",
                "symbol": "BTCUSDT",
                "cohort": "whale",
                "side": "short",
                "position_qty": 12.0,
                "position_usdt": 12.0,
                "avg_entry_price": 33.0,
                "raw_json": "{}",
            },
        ],
        db_path=db_path,
    )


def test_format_table_renders_headers_and_rows() -> None:
    table = format_table([{"symbol": "BTCUSDT", "value": 1.23}])
    assert "symbol" in table
    assert "BTCUSDT" in table


def test_run_query_latest_returns_pivoted_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "smart_signal.sqlite3"
    _seed(db_path)

    args = Namespace(command="latest", db_path=str(db_path), symbol=None, limit=20, format="table")
    rows = run_query(args)
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["trader_long_qty"] == 20.0
    assert rows[0]["whale_short_avg_entry_price"] == 33.0
    assert rows[0]["market_long_short_ratio"] == 2.0


def test_run_query_snapshots_defaults_to_latest_ts(tmp_path: Path) -> None:
    db_path = tmp_path / "smart_signal.sqlite3"
    _seed(db_path)

    args = Namespace(
        command="snapshots",
        db_path=str(db_path),
        ts_utc=None,
        symbol="BTCUSDT",
        cohort="trader",
        side=None,
        limit=10,
        format="table",
    )
    rows = run_query(args)
    assert len(rows) == 2
    assert {row["side"] for row in rows} == {"long", "short"}


def test_fetch_symbol_timeseries_adds_change_rates(tmp_path: Path) -> None:
    db_path = tmp_path / "smart_signal.sqlite3"
    _seed(db_path)

    rows = fetch_symbol_timeseries(db_path=db_path, symbol="BTCUSDT", limit=10)
    assert len(rows) == 2
    assert rows[-1]["trader_long_short_ratio"] == 2.0
    assert rows[-1]["trader_long_qty_change_rate"] == 1.0
