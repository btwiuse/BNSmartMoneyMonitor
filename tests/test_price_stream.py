from __future__ import annotations

from pathlib import Path

from smart_signal.price_stream import apply_ticker_updates, load_price_snapshot, price_snapshot_rows, save_price_snapshot


def test_apply_ticker_updates_accepts_all_market_ticker_array() -> None:
    prices: dict[str, dict[str, object]] = {}

    updated = apply_ticker_updates(
        prices,
        [
            {"s": "BTCUSDT", "c": "68000.12", "E": 1710000000000},
            {"s": "ETHUSDT", "c": "3500.5", "E": 1710000001000},
        ],
    )

    assert updated == 2
    assert prices["BTCUSDT"]["last_price"] == 68000.12
    assert prices["ETHUSDT"]["event_time_ms"] == 1710000001000


def test_save_and_load_price_snapshot_roundtrip(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "prices.json"
    save_price_snapshot(
        {
            "BTCUSDT": {"last_price": 68000.12, "event_time_ms": 1710000000000},
        },
        snapshot_path,
    )

    payload = load_price_snapshot(snapshot_path)

    assert payload["symbol_count"] == 1
    assert payload["prices"]["BTCUSDT"]["last_price"] == 68000.12


def test_price_snapshot_rows_maps_prices_to_db_rows() -> None:
    rows = price_snapshot_rows(
        "2026-03-10T02:35:00Z",
        {
            "prices": {
                "BTCUSDT": {"last_price": 68000.12, "event_time_ms": 1710000000000},
                "ETHUSDT": {"last_price": 3500.5, "event_time_ms": 1710000001000},
            }
        },
    )

    assert rows == [
        {
            "ts_utc": "2026-03-10T02:35:00Z",
            "symbol": "BTCUSDT",
            "last_price": 68000.12,
            "event_time_ms": 1710000000000,
            "raw_json": {"last_price": 68000.12, "event_time_ms": 1710000000000},
        },
        {
            "ts_utc": "2026-03-10T02:35:00Z",
            "symbol": "ETHUSDT",
            "last_price": 3500.5,
            "event_time_ms": 1710000001000,
            "raw_json": {"last_price": 3500.5, "event_time_ms": 1710000001000},
        },
    ]
