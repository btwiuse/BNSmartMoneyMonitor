"""SQLite persistence helpers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator


DEFAULT_DB_PATH = Path("data") / "smart_signal.sqlite3"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS smart_signal_snapshot (
    ts_utc TEXT NOT NULL,
    symbol TEXT NOT NULL,
    cohort TEXT NOT NULL,
    side TEXT NOT NULL,
    position_qty REAL,
    position_usdt REAL,
    avg_entry_price REAL,
    raw_json TEXT,
    PRIMARY KEY (ts_utc, symbol, cohort, side)
);

CREATE TABLE IF NOT EXISTS futures_price_snapshot (
    ts_utc TEXT NOT NULL,
    symbol TEXT NOT NULL,
    last_price REAL,
    event_time_ms INTEGER,
    raw_json TEXT,
    PRIMARY KEY (ts_utc, symbol)
);
"""

UPSERT_SQL = """
INSERT INTO smart_signal_snapshot (
    ts_utc,
    symbol,
    cohort,
    side,
    position_qty,
    position_usdt,
    avg_entry_price,
    raw_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(ts_utc, symbol, cohort, side) DO UPDATE SET
    position_qty = excluded.position_qty,
    position_usdt = excluded.position_usdt,
    avg_entry_price = excluded.avg_entry_price,
    raw_json = excluded.raw_json;
"""

PRICE_UPSERT_SQL = """
INSERT INTO futures_price_snapshot (
    ts_utc,
    symbol,
    last_price,
    event_time_ms,
    raw_json
) VALUES (?, ?, ?, ?, ?)
ON CONFLICT(ts_utc, symbol) DO UPDATE SET
    last_price = excluded.last_price,
    event_time_ms = excluded.event_time_ms,
    raw_json = excluded.raw_json;
"""


@dataclass(slots=True)
class SnapshotRecord:
    ts_utc: str
    symbol: str
    cohort: str
    side: str
    position_qty: float | None
    position_usdt: float | None
    avg_entry_price: float | None
    raw_json: str | None

    @classmethod
    def from_mapping(cls, payload: dict) -> "SnapshotRecord":
        """Create a strongly-typed record from a dict-like payload."""
        return cls(
            ts_utc=payload["ts_utc"],
            symbol=payload["symbol"],
            cohort=payload["cohort"],
            side=payload["side"],
            position_qty=payload.get("position_qty"),
            position_usdt=payload.get("position_usdt"),
            avg_entry_price=payload.get("avg_entry_price"),
            raw_json=payload.get("raw_json"),
        )

    def as_sql_params(self) -> tuple[str, str, str, str, float | None, float | None, float | None, str | None]:
        return (
            self.ts_utc,
            self.symbol,
            self.cohort,
            self.side,
            self.position_qty,
            self.position_usdt,
            self.avg_entry_price,
            self.raw_json,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class PriceSnapshotRecord:
    ts_utc: str
    symbol: str
    last_price: float | None
    event_time_ms: int | None
    raw_json: str | None

    @classmethod
    def from_mapping(cls, payload: dict) -> "PriceSnapshotRecord":
        return cls(
            ts_utc=payload["ts_utc"],
            symbol=payload["symbol"],
            last_price=payload.get("last_price"),
            event_time_ms=payload.get("event_time_ms"),
            raw_json=payload.get("raw_json"),
        )

    def as_sql_params(self) -> tuple[str, str, float | None, int | None, str | None]:
        return (
            self.ts_utc,
            self.symbol,
            self.last_price,
            self.event_time_ms,
            self.raw_json,
        )


def floor_utc_to_5m(dt: datetime | None = None) -> str:
    """Return an ISO8601 UTC timestamp rounded down to the nearest 5 minutes."""
    current = dt or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)
    floored = current.replace(minute=(current.minute // 5) * 5, second=0, microsecond=0)
    return floored.isoformat().replace("+00:00", "Z")


def ensure_parent_dir(db_path: str | Path) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect(db_path: str | Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    path = ensure_parent_dir(db_path)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_column(conn, "smart_signal_snapshot", "position_qty", "REAL")


def coerce_raw_json(raw_payload: str | dict | list | None) -> str | None:
    if raw_payload is None or isinstance(raw_payload, str):
        return raw_payload
    return json.dumps(raw_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def save_snapshot(
    record: SnapshotRecord | dict,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    save_snapshots([record], db_path=db_path)


def save_snapshots(
    records: Iterable[SnapshotRecord | dict],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    prepared: list[SnapshotRecord] = []
    for record in records:
        snapshot = record if isinstance(record, SnapshotRecord) else SnapshotRecord.from_mapping(record)
        prepared.append(
            SnapshotRecord(
                ts_utc=snapshot.ts_utc,
                symbol=snapshot.symbol,
                cohort=snapshot.cohort,
                side=snapshot.side,
                position_qty=snapshot.position_qty,
                position_usdt=snapshot.position_usdt,
                avg_entry_price=snapshot.avg_entry_price,
                raw_json=coerce_raw_json(snapshot.raw_json),
            )
        )

    if not prepared:
        return 0

    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executemany(UPSERT_SQL, [record.as_sql_params() for record in prepared])
    return len(prepared)


def fetch_latest_ts(db_path: str | Path = DEFAULT_DB_PATH) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT MAX(ts_utc) AS ts_utc FROM smart_signal_snapshot").fetchone()
    if row is None:
        return None
    return row["ts_utc"]


def fetch_distinct_symbols(db_path: str | Path = DEFAULT_DB_PATH) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT symbol FROM smart_signal_snapshot ORDER BY symbol").fetchall()
    return [str(row["symbol"]) for row in rows if row["symbol"]]


def save_price_snapshot(
    record: PriceSnapshotRecord | dict,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    save_price_snapshots([record], db_path=db_path)


def save_price_snapshots(
    records: Iterable[PriceSnapshotRecord | dict],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    prepared: list[PriceSnapshotRecord] = []
    for record in records:
        snapshot = record if isinstance(record, PriceSnapshotRecord) else PriceSnapshotRecord.from_mapping(record)
        prepared.append(
            PriceSnapshotRecord(
                ts_utc=snapshot.ts_utc,
                symbol=snapshot.symbol,
                last_price=snapshot.last_price,
                event_time_ms=snapshot.event_time_ms,
                raw_json=coerce_raw_json(snapshot.raw_json),
            )
        )

    if not prepared:
        return 0

    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executemany(PRICE_UPSERT_SQL, [record.as_sql_params() for record in prepared])
    return len(prepared)


def fetch_previous_ts(ts_utc: str, db_path: str | Path = DEFAULT_DB_PATH) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(ts_utc) AS ts_utc FROM smart_signal_snapshot WHERE ts_utc < ?",
            (ts_utc,),
        ).fetchone()
    if row is None:
        return None
    return row["ts_utc"]


def fetch_snapshots(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    ts_utc: str | None = None,
    symbol: str | None = None,
    cohort: str | None = None,
    side: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    where_clauses: list[str] = []
    params: list[Any] = []

    if ts_utc:
        where_clauses.append("ts_utc = ?")
        params.append(ts_utc)
    if symbol:
        where_clauses.append("symbol = ?")
        params.append(symbol.upper())
    if cohort:
        where_clauses.append("cohort = ?")
        params.append(cohort.lower())
    if side:
        where_clauses.append("side = ?")
        params.append(side.lower())

    query = """
    SELECT ts_utc, symbol, cohort, side, position_qty, position_usdt, avg_entry_price, raw_json
    FROM smart_signal_snapshot
    """
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY ts_utc DESC, symbol, cohort, side LIMIT ?"
    params.append(limit)

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_latest_pivot(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    symbol: str | None = None,
    limit: int = 100,
    sort_by: str = "symbol",
    sort_order: str = "asc",
    min_position_qty: float | None = None,
) -> list[dict[str, Any]]:
    latest_ts = fetch_latest_ts(db_path=db_path)
    if latest_ts is None:
        return []

    previous_ts = fetch_previous_ts(latest_ts, db_path=db_path)
    latest_rows = fetch_pivot_by_ts(db_path=db_path, ts_utc=latest_ts, symbol=symbol, limit=5000)
    previous_rows = fetch_pivot_by_ts(db_path=db_path, ts_utc=previous_ts, symbol=symbol, limit=5000) if previous_ts else []
    previous_by_symbol = {row["symbol"]: row for row in previous_rows}

    enriched = [enrich_pivot_row(row, previous_by_symbol.get(row["symbol"])) for row in latest_rows]
    if min_position_qty is not None:
        enriched = [
            row
            for row in enriched
            if max(
                row.get("trader_long_qty") or 0.0,
                row.get("trader_short_qty") or 0.0,
                row.get("whale_long_qty") or 0.0,
                row.get("whale_short_qty") or 0.0,
            )
            >= min_position_qty
        ]

    reverse = sort_order.lower() == "desc"
    non_null = [row for row in enriched if row.get(sort_by) is not None]
    null_rows = [row for row in enriched if row.get(sort_by) is None]
    non_null.sort(key=lambda row: row.get(sort_by), reverse=reverse)
    return [*non_null, *null_rows][:limit]


def fetch_pivot_by_ts(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    ts_utc: str | None,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if ts_utc is None:
        return []

    params: list[Any] = [ts_utc]
    symbol_clause = ""
    if symbol:
        symbol_clause = " AND symbol = ?"
        params.append(symbol.upper())

    params.append(limit)

    query = f"""
    SELECT
        ts_utc,
        symbol,
        MAX(CASE WHEN cohort = 'trader' AND side = 'long' THEN position_qty END) AS trader_long_qty,
        MAX(CASE WHEN cohort = 'trader' AND side = 'short' THEN position_qty END) AS trader_short_qty,
        MAX(CASE WHEN cohort = 'whale' AND side = 'long' THEN position_qty END) AS whale_long_qty,
        MAX(CASE WHEN cohort = 'whale' AND side = 'short' THEN position_qty END) AS whale_short_qty,
        MAX(CASE WHEN cohort = 'trader' AND side = 'long' THEN avg_entry_price END) AS trader_long_avg_entry_price,
        MAX(CASE WHEN cohort = 'trader' AND side = 'short' THEN avg_entry_price END) AS trader_short_avg_entry_price,
        MAX(CASE WHEN cohort = 'whale' AND side = 'long' THEN avg_entry_price END) AS whale_long_avg_entry_price,
        MAX(CASE WHEN cohort = 'whale' AND side = 'short' THEN avg_entry_price END) AS whale_short_avg_entry_price
    FROM smart_signal_snapshot
    WHERE ts_utc = ? {symbol_clause}
    GROUP BY ts_utc, symbol
    ORDER BY symbol
    LIMIT ?
    """

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_symbol_timeseries(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    symbol: str,
    limit: int = 120,
) -> list[dict[str, Any]]:
    query = """
    SELECT
        ts_utc,
        symbol,
        MAX(CASE WHEN cohort = 'trader' AND side = 'long' THEN position_qty END) AS trader_long_qty,
        MAX(CASE WHEN cohort = 'trader' AND side = 'short' THEN position_qty END) AS trader_short_qty,
        MAX(CASE WHEN cohort = 'whale' AND side = 'long' THEN position_qty END) AS whale_long_qty,
        MAX(CASE WHEN cohort = 'whale' AND side = 'short' THEN position_qty END) AS whale_short_qty,
        MAX(CASE WHEN cohort = 'trader' AND side = 'long' THEN avg_entry_price END) AS trader_long_avg_entry_price,
        MAX(CASE WHEN cohort = 'trader' AND side = 'short' THEN avg_entry_price END) AS trader_short_avg_entry_price,
        MAX(CASE WHEN cohort = 'whale' AND side = 'long' THEN avg_entry_price END) AS whale_long_avg_entry_price,
        MAX(CASE WHEN cohort = 'whale' AND side = 'short' THEN avg_entry_price END) AS whale_short_avg_entry_price
    FROM smart_signal_snapshot
    WHERE symbol = ?
    GROUP BY ts_utc, symbol
    ORDER BY ts_utc DESC
    LIMIT ?
    """
    with connect(db_path) as conn:
        rows = conn.execute(query, (symbol.upper(), limit)).fetchall()

    descending = [dict(row) for row in rows]
    descending.reverse()

    enriched: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for row in descending:
        enriched_row = enrich_pivot_row(row, previous)
        enriched.append(enriched_row)
        previous = row
    return enriched


def enrich_pivot_row(row: dict[str, Any], previous_row: dict[str, Any] | None = None) -> dict[str, Any]:
    trader_long = row.get("trader_long_qty")
    trader_short = row.get("trader_short_qty")
    whale_long = row.get("whale_long_qty")
    whale_short = row.get("whale_short_qty")

    enriched = dict(row)
    enriched["trader_long_short_ratio"] = _safe_divide(trader_long, trader_short)
    enriched["whale_long_short_ratio"] = _safe_divide(whale_long, whale_short)
    enriched["market_long_short_ratio"] = _safe_divide(
        (trader_long or 0.0) + (whale_long or 0.0),
        (trader_short or 0.0) + (whale_short or 0.0),
    )
    enriched["trader_net_qty"] = (trader_long or 0.0) - (trader_short or 0.0)
    enriched["whale_net_qty"] = (whale_long or 0.0) - (whale_short or 0.0)

    for key in (
        "trader_long_qty",
        "trader_short_qty",
        "whale_long_qty",
        "whale_short_qty",
    ):
        previous_value = previous_row.get(key) if previous_row else None
        enriched[f"{key}_change_rate"] = _change_rate(row.get(key), previous_value)

    return enriched


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _change_rate(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous
