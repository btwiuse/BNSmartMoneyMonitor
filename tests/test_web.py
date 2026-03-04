from __future__ import annotations

from pathlib import Path

from smart_signal.db import fetch_latest_pivot, init_db, save_snapshots
from smart_signal.price_stream import save_price_snapshot
from smart_signal.web import _parse_float, enrich_latest_rows_with_prices, make_meta_payload, make_price_payload, parse_positive_int, sort_rows


def test_parse_positive_int_clamps_values() -> None:
    assert parse_positive_int(None, 10) == 10
    assert parse_positive_int("abc", 10) == 10
    assert parse_positive_int("0", 10, minimum=1) == 1
    assert parse_positive_int("9999", 10, maximum=100) == 100


def test_make_meta_payload_reports_latest_ts_and_symbol_count(tmp_path: Path) -> None:
    db_path = tmp_path / "smart_signal.sqlite3"
    price_snapshot_path = tmp_path / "prices.json"
    init_db(db_path)
    save_snapshots(
        [
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "trader",
                "side": "long",
                "position_qty": 1.0,
                "position_usdt": 1.0,
                "avg_entry_price": 2.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "trader",
                "side": "short",
                "position_qty": 1.0,
                "position_usdt": 1.0,
                "avg_entry_price": 2.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "whale",
                "side": "long",
                "position_qty": 1.0,
                "position_usdt": 1.0,
                "avg_entry_price": 2.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "whale",
                "side": "short",
                "position_qty": 1.0,
                "position_usdt": 1.0,
                "avg_entry_price": 2.0,
                "raw_json": "{}",
            },
        ],
        db_path=db_path,
    )
    save_price_snapshot(
        {
            "BTCUSDT": {"last_price": 68000.12, "event_time_ms": 1710000000000},
        },
        price_snapshot_path,
    )

    payload = make_meta_payload(db_path, price_snapshot_path)
    assert payload["latest_ts"] == "2026-03-04T03:00:00Z"
    assert payload["symbol_count"] == 1
    assert payload["ws_price_symbol_count"] == 1


def test_make_price_payload_reads_latest_ws_price(tmp_path: Path) -> None:
    price_snapshot_path = tmp_path / "prices.json"
    save_price_snapshot(
        {
            "BTCUSDT": {"last_price": 68000.12, "event_time_ms": 1710000000000},
        },
        price_snapshot_path,
    )

    payload = make_price_payload("btcusdt", price_snapshot_path)

    assert payload["symbol"] == "BTCUSDT"
    assert payload["last_price"] == 68000.12


def test_enrich_latest_rows_with_prices_merges_ws_last_price(tmp_path: Path) -> None:
    db_path = tmp_path / "smart_signal.sqlite3"
    price_snapshot_path = tmp_path / "prices.json"
    init_db(db_path)
    save_snapshots(
        [
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "trader",
                "side": "long",
                "position_qty": 1.0,
                "position_usdt": None,
                "avg_entry_price": 2.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "trader",
                "side": "short",
                "position_qty": 1.0,
                "position_usdt": None,
                "avg_entry_price": 2.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "whale",
                "side": "long",
                "position_qty": 1.0,
                "position_usdt": None,
                "avg_entry_price": 2.0,
                "raw_json": "{}",
            },
            {
                "ts_utc": "2026-03-04T03:00:00Z",
                "symbol": "BTCUSDT",
                "cohort": "whale",
                "side": "short",
                "position_qty": 1.0,
                "position_usdt": None,
                "avg_entry_price": 2.0,
                "raw_json": "{}",
            },
        ],
        db_path=db_path,
    )
    save_price_snapshot(
        {
            "BTCUSDT": {"last_price": 68000.12, "event_time_ms": 1710000000000},
        },
        price_snapshot_path,
    )

    rows = fetch_latest_pivot(db_path=db_path, limit=10)
    enriched = enrich_latest_rows_with_prices(rows, price_snapshot_path)

    assert enriched[0]["ws_last_price"] == 68000.12


def test_sort_rows_orders_ws_prices_descending() -> None:
    rows = [
        {"symbol": "BTCUSDT", "ws_last_price": 68000.12},
        {"symbol": "ETHUSDT", "ws_last_price": 3500.5},
        {"symbol": "XRPUSDT", "ws_last_price": None},
    ]

    sorted_rows = sort_rows(rows, "ws_last_price", "desc")

    assert [row["symbol"] for row in sorted_rows] == ["BTCUSDT", "ETHUSDT", "XRPUSDT"]


def test_parse_float_handles_invalid_values() -> None:
    assert _parse_float(None) is None
    assert _parse_float("") is None
    assert _parse_float("abc") is None
    assert _parse_float("12.5") == 12.5
