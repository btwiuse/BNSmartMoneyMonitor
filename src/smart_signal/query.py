"""SQLite query helpers and CLI for Smart Signal snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from smart_signal.db import DEFAULT_DB_PATH, fetch_latest_pivot, fetch_latest_ts, fetch_snapshots


def format_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""

    headers = list(rows[0].keys())
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(_stringify(row.get(header))))

    separator = " | "
    header_line = separator.join(header.ljust(widths[header]) for header in headers)
    body_lines = [
        separator.join(_stringify(row.get(header)).ljust(widths[header]) for header in headers)
        for row in rows
    ]
    return "\n".join([header_line, "-+-".join("-" * widths[header] for header in headers), *body_lines])


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Smart Signal snapshots from SQLite.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--format", choices=("table", "json"), default="table", help="Output format.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    latest_parser = subparsers.add_parser("latest", help="Show the latest timestamp pivoted by symbol.")
    latest_parser.add_argument("--symbol", help="Restrict to a single symbol.")
    latest_parser.add_argument("--limit", type=int, default=20, help="Maximum number of symbols to return.")

    snapshots_parser = subparsers.add_parser("snapshots", help="Show raw snapshot rows.")
    snapshots_parser.add_argument("--ts-utc", help="Exact UTC bucket timestamp.")
    snapshots_parser.add_argument("--symbol", help="Restrict to a single symbol.")
    snapshots_parser.add_argument("--cohort", choices=("trader", "whale"))
    snapshots_parser.add_argument("--side", choices=("long", "short"))
    snapshots_parser.add_argument("--limit", type=int, default=50, help="Maximum number of rows to return.")

    history_parser = subparsers.add_parser("history", help="Show historical rows for one symbol.")
    history_parser.add_argument("symbol", help="Target symbol.")
    history_parser.add_argument("--limit", type=int, default=40, help="Maximum number of rows to return.")

    return parser.parse_args()


def run_query(args: argparse.Namespace) -> list[dict[str, Any]]:
    db_path = Path(args.db_path)

    if args.command == "latest":
        return fetch_latest_pivot(db_path=db_path, symbol=args.symbol, limit=args.limit)

    if args.command == "snapshots":
        ts_utc = args.ts_utc or fetch_latest_ts(db_path=db_path)
        return fetch_snapshots(
            db_path=db_path,
            ts_utc=ts_utc,
            symbol=args.symbol,
            cohort=args.cohort,
            side=args.side,
            limit=args.limit,
        )

    if args.command == "history":
        return fetch_snapshots(db_path=db_path, symbol=args.symbol, limit=args.limit)

    raise RuntimeError(f"unknown command: {args.command}")


def emit(rows: list[dict[str, Any]], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(rows, ensure_ascii=True, indent=2, sort_keys=True))
        return

    if not rows:
        print("No rows found.")
        return
    print(format_table(rows))


def main() -> None:
    args = parse_args()
    rows = run_query(args)
    emit(rows, args.format)


if __name__ == "__main__":
    main()
