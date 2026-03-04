"""JSON parsing helpers for Binance Smart Signal payloads."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


POSITION_KEYS = {
    "positionusd",
    "positionusdt",
    "position_usdt",
    "position",
    "positionvalue",
}
AVG_ENTRY_KEYS = {
    "avgentryprice",
    "avg_entry_price",
    "entryprice",
    "averageentryprice",
}
LONG_ALIASES = {"long", "buy", "bull", "bullish"}
SHORT_ALIASES = {"short", "sell", "bear", "bearish"}
NUMERIC_TOKEN_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*([KMBT]?)\s*$", re.IGNORECASE)
FLAT_KEY_RE = re.compile(r"^(long|short)[_\-]?(.*)$", re.IGNORECASE)

MULTIPLIERS = {
    "": 1.0,
    "K": 1_000.0,
    "M": 1_000_000.0,
    "B": 1_000_000_000.0,
    "T": 1_000_000_000_000.0,
}


@dataclass(slots=True)
class SideSnapshot:
    side: str
    position_qty: float | None = None
    position_usdt: float | None = None
    avg_entry_price: float | None = None
    source_path: str | None = None


@dataclass(slots=True)
class ParsedSignal:
    long: SideSnapshot
    short: SideSnapshot

    def as_rows(self, *, ts_utc: str, symbol: str, cohort: str, raw_json: str | None) -> list[dict]:
        return [
            {
                "ts_utc": ts_utc,
                "symbol": symbol,
                "cohort": cohort,
                "side": side_snapshot.side,
                "position_qty": side_snapshot.position_qty,
                "position_usdt": side_snapshot.position_usdt,
                "avg_entry_price": side_snapshot.avg_entry_price,
                "raw_json": raw_json,
            }
            for side_snapshot in (self.long, self.short)
        ]


def build_position_usdt(quantity: Any, current_price: Any) -> float | None:
    normalized_qty = normalize_number(quantity)
    normalized_price = normalize_number(current_price)
    if normalized_qty is None or normalized_price is None:
        return None
    return normalized_qty * normalized_price


def normalize_number(value: Any) -> float | None:
    """Normalize Binance UI numeric strings such as 951.89M or 2.41B."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)

    text = str(value).strip()
    if not text or text in {"--", "N/A", "null", "None"}:
        return None

    compact = text.replace(",", "").replace("$", "").replace("USDT", "").replace("USD", "").strip()
    match = NUMERIC_TOKEN_RE.match(compact)
    if not match:
        return None

    number, suffix = match.groups()
    return float(number) * MULTIPLIERS[suffix.upper()]


def parse_signal_payload(payload: Any) -> ParsedSignal:
    """Extract long/short metrics from loosely structured Smart Signal payloads."""
    overview_parsed = parse_overview_payload(payload)
    if overview_parsed is not None:
        return overview_parsed

    snapshots = {
        "long": SideSnapshot(side="long"),
        "short": SideSnapshot(side="short"),
    }
    _walk_payload(payload, snapshots, "$")
    return ParsedSignal(long=snapshots["long"], short=snapshots["short"])


def parse_overview_payload(payload: Any, *, current_price: Any | None = None, cohort: str = "trader") -> ParsedSignal | None:
    """Parse Binance Smart Signal overview payload for trader or whale cohorts."""
    if not isinstance(payload, dict):
        return None

    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return None

    prefix = "Traders" if cohort == "trader" else "Whales"
    long_qty_key = f"long{prefix}Qty"
    short_qty_key = f"short{prefix}Qty"
    long_avg_key = f"long{prefix}AvgEntryPrice"
    short_avg_key = f"short{prefix}AvgEntryPrice"

    if long_qty_key not in data and short_qty_key not in data:
        return None

    return ParsedSignal(
        long=SideSnapshot(
            side="long",
            position_qty=normalize_number(data.get(long_qty_key)),
            position_usdt=build_position_usdt(data.get(long_qty_key), current_price),
            avg_entry_price=normalize_number(data.get(long_avg_key)),
            source_path=f"$.data.{long_qty_key}",
        ),
        short=SideSnapshot(
            side="short",
            position_qty=normalize_number(data.get(short_qty_key)),
            position_usdt=build_position_usdt(data.get(short_qty_key), current_price),
            avg_entry_price=normalize_number(data.get(short_avg_key)),
            source_path=f"$.data.{short_qty_key}",
        ),
    )


def _walk_payload(node: Any, snapshots: dict[str, SideSnapshot], path: str) -> None:
    if isinstance(node, dict):
        _extract_nested_side_objects(node, snapshots, path)
        _extract_flattened_side_keys(node, snapshots, path)
        _extract_side_record(node, snapshots, path)

        for key, value in node.items():
            _walk_payload(value, snapshots, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk_payload(item, snapshots, f"{path}[{index}]")


def _extract_nested_side_objects(node: dict[str, Any], snapshots: dict[str, SideSnapshot], path: str) -> None:
    for side in ("long", "short"):
        raw_value = node.get(side)
        if isinstance(raw_value, dict):
            _merge_side_values(snapshots[side], raw_value, f"{path}.{side}")


def _extract_flattened_side_keys(node: dict[str, Any], snapshots: dict[str, SideSnapshot], path: str) -> None:
    grouped: dict[str, dict[str, Any]] = {"long": {}, "short": {}}
    for key, value in node.items():
        if not isinstance(key, str):
            continue
        match = FLAT_KEY_RE.match(key)
        if not match:
            continue
        side, tail = match.groups()
        grouped[side.lower()][tail.lower()] = value

    for side, values in grouped.items():
        if values:
            _merge_side_values(snapshots[side], values, f"{path}.{side}_flat")


def _extract_side_record(node: dict[str, Any], snapshots: dict[str, SideSnapshot], path: str) -> None:
    side = _coerce_side(node.get("side") or node.get("positionSide") or node.get("direction"))
    if side is None:
        return
    _merge_side_values(snapshots[side], node, path)


def _coerce_side(value: Any) -> str | None:
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if lowered in LONG_ALIASES:
        return "long"
    if lowered in SHORT_ALIASES:
        return "short"
    return None


def _merge_side_values(target: SideSnapshot, source: dict[str, Any], path: str) -> None:
    position = _pick_numeric_value(source, POSITION_KEYS)
    avg_entry = _pick_numeric_value(source, AVG_ENTRY_KEYS)

    if position is not None:
        target.position_qty = position
        target.position_usdt = position
        target.source_path = path
    if avg_entry is not None:
        target.avg_entry_price = avg_entry
        target.source_path = path


def _pick_numeric_value(source: dict[str, Any], aliases: set[str]) -> float | None:
    normalized_map = {str(key).replace("-", "").replace("_", "").lower(): value for key, value in source.items()}
    for alias in aliases:
        normalized_alias = alias.replace("-", "").replace("_", "").lower()
        if normalized_alias in normalized_map:
            return normalize_number(normalized_map[normalized_alias])
    return None
