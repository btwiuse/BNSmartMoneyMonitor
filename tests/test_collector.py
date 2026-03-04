from __future__ import annotations

from smart_signal.collector import (
    CapturedPayload,
    build_overview_api_url,
    captures_to_rows,
    payload_contains_signal_fields,
)


def test_payload_contains_signal_fields_detects_nested_signal_shape() -> None:
    payload = {"data": {"rows": [{"avgEntryPrice": "100", "positionUSDT": "2.1M"}]}}
    assert payload_contains_signal_fields(payload) is True


def test_payload_contains_signal_fields_rejects_unrelated_payload() -> None:
    assert payload_contains_signal_fields({"foo": {"bar": 1}}) is False


def test_captures_to_rows_creates_null_rows_for_failed_parse() -> None:
    capture = CapturedPayload(symbol="BTCUSDT", cohort="trader", raw_json='{"error":"x"}', parsed=None, error="x")
    rows = captures_to_rows("2026-03-04T12:00:00Z", capture, "BTCUSDT")
    assert rows == [
        {
            "ts_utc": "2026-03-04T12:00:00Z",
            "symbol": "BTCUSDT",
            "cohort": "trader",
            "side": "long",
            "position_qty": None,
            "position_usdt": None,
            "avg_entry_price": None,
            "raw_json": '{"error":"x"}',
        },
        {
            "ts_utc": "2026-03-04T12:00:00Z",
            "symbol": "BTCUSDT",
            "cohort": "trader",
            "side": "short",
            "position_qty": None,
            "position_usdt": None,
            "avg_entry_price": None,
            "raw_json": '{"error":"x"}',
        },
    ]


def test_payload_contains_signal_fields_detects_overview_shape() -> None:
    payload = {"data": {"longTradersQty": 1, "shortWhalesQty": 2}}
    assert payload_contains_signal_fields(payload) is True


def test_build_overview_api_url_formats_symbol() -> None:
    assert build_overview_api_url("btcusdt") == (
        "https://www.binance.com/bapi/futures/v1/public/future/smart-money/signal/overview?symbol=BTCUSDT"
    )
