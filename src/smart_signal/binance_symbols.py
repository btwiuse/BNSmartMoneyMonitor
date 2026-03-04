"""Binance Futures symbol discovery helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
DEFAULT_STAGE1_SYMBOLS = ("BTCUSDT", "ETHUSDT")
DEFAULT_SYMBOL_LIST_PATH = Path("config") / "binance_usdt_perpetual_symbols.txt"


class SymbolFetchError(RuntimeError):
    """Raised when Binance symbol discovery fails."""


@dataclass(slots=True)
class SymbolUniverse:
    symbols: list[str]
    source_url: str = EXCHANGE_INFO_URL


def fetch_exchange_info(timeout: int = 15) -> dict[str, Any]:
    request = Request(
        EXCHANGE_INFO_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "smart-signal-collector/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SymbolFetchError(f"failed to fetch Binance exchange info: {exc}") from exc


def load_symbol_list(list_path: str | Path = DEFAULT_SYMBOL_LIST_PATH) -> list[str] | None:
    path = Path(list_path)
    if not path.exists():
        return None
    try:
        symbols = [line.strip().upper() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        raise SymbolFetchError(f"failed to read symbol list: {exc}") from exc
    return sorted(set(symbols))


def save_symbol_list(symbols: Iterable[str], list_path: str | Path = DEFAULT_SYMBOL_LIST_PATH) -> Path:
    path = Path(list_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = sorted({symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()})
    path.write_text("\n".join(normalized) + "\n", encoding="utf-8")
    return path


def filter_usdt_perpetual_symbols(exchange_info: dict[str, Any]) -> list[str]:
    symbols: list[str] = []
    for item in exchange_info.get("symbols", []):
        if not isinstance(item, dict):
            continue
        if item.get("contractType") != "PERPETUAL":
            continue
        if item.get("quoteAsset") != "USDT":
            continue
        if item.get("status") != "TRADING":
            continue
        symbol = item.get("symbol")
        if isinstance(symbol, str) and symbol:
            symbols.append(symbol)
    return sorted(set(symbols))


def apply_allowlist(symbols: Iterable[str], allowlist: Iterable[str] | None = None) -> list[str]:
    if allowlist is None:
        return list(symbols)
    allowed = {symbol.upper() for symbol in allowlist}
    return [symbol for symbol in symbols if symbol.upper() in allowed]


def get_target_symbols(
    *,
    stage1_only: bool = False,
    allowlist: Iterable[str] | None = None,
    timeout: int = 15,
    list_path: str | Path = DEFAULT_SYMBOL_LIST_PATH,
    refresh: bool = False,
) -> SymbolUniverse:
    symbols = None if refresh else load_symbol_list(list_path)
    source_url = str(Path(list_path))

    if symbols is None:
        try:
            exchange_info = fetch_exchange_info(timeout=timeout)
            symbols = filter_usdt_perpetual_symbols(exchange_info)
            save_symbol_list(symbols, list_path)
            source_url = EXCHANGE_INFO_URL
        except SymbolFetchError:
            fallback = load_symbol_list(list_path)
            if fallback is None:
                raise
            symbols = fallback
            source_url = str(Path(list_path))

    if stage1_only and allowlist is None:
        allowlist = DEFAULT_STAGE1_SYMBOLS
    return SymbolUniverse(symbols=apply_allowlist(symbols, allowlist), source_url=source_url)
