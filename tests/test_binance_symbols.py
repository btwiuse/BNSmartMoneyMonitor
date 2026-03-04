from __future__ import annotations

from pathlib import Path

from smart_signal.binance_symbols import (
    SymbolFetchError,
    apply_allowlist,
    filter_usdt_perpetual_symbols,
    get_target_symbols,
    load_symbol_list,
    save_symbol_list,
)


def test_filter_usdt_perpetual_symbols_filters_expected_rows() -> None:
    exchange_info = {
        "symbols": [
            {"symbol": "BTCUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING"},
            {"symbol": "ETHUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING"},
            {"symbol": "BTCUSD_PERP", "contractType": "PERPETUAL", "quoteAsset": "USD", "status": "TRADING"},
            {"symbol": "BNBUSDT_240628", "contractType": "CURRENT_QUARTER", "quoteAsset": "USDT", "status": "TRADING"},
            {"symbol": "XRPUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "BREAK"},
        ]
    }

    assert filter_usdt_perpetual_symbols(exchange_info) == ["BTCUSDT", "ETHUSDT"]


def test_apply_allowlist_preserves_matching_order() -> None:
    assert apply_allowlist(["BTCUSDT", "ETHUSDT", "SOLUSDT"], ["ETHUSDT", "SOLUSDT"]) == [
        "ETHUSDT",
        "SOLUSDT",
    ]


def test_get_target_symbols_defaults_to_full_universe(monkeypatch) -> None:
    monkeypatch.setattr(
        "smart_signal.binance_symbols.load_symbol_list",
        lambda list_path=None: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    )

    universe = get_target_symbols()

    assert universe.symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def test_get_target_symbols_stage1_only_uses_validation_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(
        "smart_signal.binance_symbols.load_symbol_list",
        lambda list_path=None: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    )

    universe = get_target_symbols(stage1_only=True)

    assert universe.symbols == ["BTCUSDT", "ETHUSDT"]


def test_save_and_load_symbol_list_roundtrip(tmp_path: Path) -> None:
    list_path = tmp_path / "symbols.txt"
    save_symbol_list(["ETHUSDT", "BTCUSDT", "BTCUSDT"], list_path)
    assert load_symbol_list(list_path) == ["BTCUSDT", "ETHUSDT"]


def test_get_target_symbols_prefers_static_list(tmp_path: Path, monkeypatch) -> None:
    list_path = tmp_path / "symbols.txt"
    save_symbol_list(["BTCUSDT", "ETHUSDT"], list_path)
    called = False

    def _boom(timeout: int = 15) -> dict:
        nonlocal called
        called = True
        raise AssertionError("network fetch should not be called when list exists")

    monkeypatch.setattr("smart_signal.binance_symbols.fetch_exchange_info", _boom)

    universe = get_target_symbols(list_path=list_path)

    assert universe.symbols == ["BTCUSDT", "ETHUSDT"]
    assert universe.source_url == str(list_path)
    assert called is False


def test_get_target_symbols_falls_back_to_static_list_on_fetch_failure(tmp_path: Path, monkeypatch) -> None:
    list_path = tmp_path / "symbols.txt"
    save_symbol_list(["BTCUSDT"], list_path)

    def _fail(timeout: int = 15) -> dict:
        raise SymbolFetchError("boom")

    monkeypatch.setattr("smart_signal.binance_symbols.fetch_exchange_info", _fail)

    universe = get_target_symbols(list_path=list_path, refresh=True)

    assert universe.symbols == ["BTCUSDT"]
    assert universe.source_url == str(list_path)
