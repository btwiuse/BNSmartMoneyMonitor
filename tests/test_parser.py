from __future__ import annotations

from smart_signal.parser import build_position_usdt, normalize_number, parse_overview_payload, parse_signal_payload


def test_normalize_number_handles_suffixes() -> None:
    assert normalize_number("951.89M") == 951_890_000.0
    assert normalize_number("2.41B") == 2_410_000_000.0
    assert normalize_number("73,905.86") == 73_905.86


def test_parse_signal_payload_handles_nested_long_short() -> None:
    payload = {
        "data": {
            "long": {
                "positionUSDT": "951.89M",
                "avgEntryPrice": "73905.86",
            },
            "short": {
                "positionUsd": "2.41B",
                "entryPrice": "74123.50",
            },
        }
    }

    parsed = parse_signal_payload(payload)

    assert parsed.long.position_qty == 951_890_000.0
    assert parsed.long.position_usdt == 951_890_000.0
    assert parsed.long.avg_entry_price == 73_905.86
    assert parsed.short.position_qty == 2_410_000_000.0
    assert parsed.short.position_usdt == 2_410_000_000.0
    assert parsed.short.avg_entry_price == 74_123.50


def test_parse_signal_payload_handles_side_records() -> None:
    payload = {
        "rows": [
            {"side": "LONG", "positionUsd": "120M", "avgEntryPrice": "50000"},
            {"side": "SHORT", "positionUSDT": "80M", "entryPrice": "49000"},
        ]
    }

    parsed = parse_signal_payload(payload)

    assert parsed.long.position_qty == 120_000_000.0
    assert parsed.long.position_usdt == 120_000_000.0
    assert parsed.short.position_qty == 80_000_000.0
    assert parsed.short.position_usdt == 80_000_000.0


def test_build_position_usdt_multiplies_quantity_by_current_price() -> None:
    assert build_position_usdt(13_762.128, 68_022.90) == 936_139_856.7312


def test_parse_overview_payload_maps_trader_fields() -> None:
    payload = {
        "data": {
            "longTradersQty": 13762.128,
            "longTradersAvgEntryPrice": 73966.58969907,
            "shortTradersQty": 35367.441,
            "shortTradersAvgEntryPrice": 83153.01504458,
        }
    }

    parsed = parse_overview_payload(payload, cohort="trader")

    assert parsed is not None
    assert parsed.long.position_qty == 13762.128
    assert parsed.long.position_usdt is None
    assert parsed.long.avg_entry_price == 73966.58969907
    assert parsed.short.position_qty == 35367.441
    assert parsed.short.position_usdt is None
    assert parsed.short.avg_entry_price == 83153.01504458
