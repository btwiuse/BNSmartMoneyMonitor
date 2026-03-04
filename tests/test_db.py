from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from smart_signal.db import fetch_distinct_symbols, floor_utc_to_5m, init_db, save_snapshot


def test_floor_utc_to_5m_rounds_down() -> None:
    dt = datetime(2026, 3, 4, 12, 7, 59, tzinfo=UTC)
    assert floor_utc_to_5m(dt) == "2026-03-04T12:05:00Z"


def test_save_snapshot_upserts(tmp_path: Path) -> None:
    db_path = tmp_path / "smart_signal.sqlite3"
    init_db(db_path)

    row = {
        "ts_utc": "2026-03-04T12:00:00Z",
        "symbol": "BTCUSDT",
        "cohort": "trader",
        "side": "long",
        "position_qty": 1.5,
        "position_usdt": 1.0,
        "avg_entry_price": 2.0,
        "raw_json": {"foo": "bar"},
    }
    save_snapshot(row, db_path=db_path)

    row["position_qty"] = 4.5
    row["position_usdt"] = None
    save_snapshot(row, db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        result = conn.execute(
            "SELECT position_qty, position_usdt, avg_entry_price, raw_json FROM smart_signal_snapshot"
        ).fetchone()
    finally:
        conn.close()

    assert result == (4.5, None, 2.0, '{"foo":"bar"}')


def test_fetch_distinct_symbols_returns_sorted_unique_values(tmp_path: Path) -> None:
    db_path = tmp_path / "smart_signal.sqlite3"
    init_db(db_path)
    save_snapshot(
        {
            "ts_utc": "2026-03-04T12:00:00Z",
            "symbol": "ETHUSDT",
            "cohort": "trader",
            "side": "long",
            "position_qty": 1.0,
            "position_usdt": None,
            "avg_entry_price": 2.0,
            "raw_json": "{}",
        },
        db_path=db_path,
    )
    save_snapshot(
        {
            "ts_utc": "2026-03-04T12:00:00Z",
            "symbol": "BTCUSDT",
            "cohort": "trader",
            "side": "long",
            "position_qty": 1.0,
            "position_usdt": None,
            "avg_entry_price": 2.0,
            "raw_json": "{}",
        },
        db_path=db_path,
    )

    assert fetch_distinct_symbols(db_path) == ["BTCUSDT", "ETHUSDT"]
