"""Lightweight web dashboard and JSON API for Smart Signal snapshots."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from smart_signal.db import DEFAULT_DB_PATH, fetch_latest_pivot, fetch_latest_ts, fetch_snapshots, fetch_symbol_timeseries
from smart_signal.logging_utils import DEFAULT_LOG_BACKUP_COUNT, DEFAULT_LOG_DIR, configure_logging, install_exception_logging
from smart_signal.price_stream import DEFAULT_PRICE_SNAPSHOT_PATH, load_price_snapshot


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
LOGGER = __import__("logging").getLogger(__name__)
PRICE_SORT_FIELDS = {"ws_last_price", "ws_price_event_time_ms"}


def parse_positive_int(value: str | None, default: int, *, minimum: int = 1, maximum: int = 1000) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def make_meta_payload(db_path: Path, price_snapshot_path: Path = DEFAULT_PRICE_SNAPSHOT_PATH) -> dict[str, Any]:
    latest_ts = fetch_latest_ts(db_path=db_path)
    latest_rows = fetch_latest_pivot(db_path=db_path, limit=5000) if latest_ts else []
    price_snapshot = load_price_snapshot(price_snapshot_path)
    return {
        "latest_ts": latest_ts,
        "symbol_count": len(latest_rows),
        "ws_price_as_of": price_snapshot.get("as_of"),
        "ws_price_symbol_count": price_snapshot.get("symbol_count", 0),
    }


def make_price_payload(symbol: str, price_snapshot_path: Path = DEFAULT_PRICE_SNAPSHOT_PATH) -> dict[str, Any]:
    payload = load_price_snapshot(price_snapshot_path)
    prices = payload.get("prices") or {}
    row = prices.get(symbol.upper())
    return {
        "symbol": symbol.upper(),
        "last_price": row.get("last_price") if isinstance(row, dict) else None,
        "event_time_ms": row.get("event_time_ms") if isinstance(row, dict) else None,
        "as_of": payload.get("as_of"),
    }


def enrich_latest_rows_with_prices(rows: list[dict[str, Any]], price_snapshot_path: Path = DEFAULT_PRICE_SNAPSHOT_PATH) -> list[dict[str, Any]]:
    payload = load_price_snapshot(price_snapshot_path)
    prices = payload.get("prices") or {}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        enriched_row = dict(row)
        price_row = prices.get(str(row.get("symbol", "")).upper())
        enriched_row["ws_last_price"] = price_row.get("last_price") if isinstance(price_row, dict) else None
        enriched_row["ws_price_event_time_ms"] = price_row.get("event_time_ms") if isinstance(price_row, dict) else None
        enriched.append(enriched_row)
    return enriched


def sort_rows(rows: list[dict[str, Any]], sort_by: str, sort_order: str) -> list[dict[str, Any]]:
    reverse = sort_order.lower() == "desc"
    non_null = [row for row in rows if row.get(sort_by) is not None]
    null_rows = [row for row in rows if row.get(sort_by) is None]
    non_null.sort(key=lambda row: row.get(sort_by), reverse=reverse)
    return [*non_null, *null_rows]


def make_handler(db_path: Path, price_snapshot_path: Path = DEFAULT_PRICE_SNAPSHOT_PATH) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api(parsed.path, parse_qs(parsed.query))
                return

            if parsed.path == "/":
                self._serve_static("index.html")
                return

            requested = parsed.path.lstrip("/")
            self._serve_static(requested)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _handle_api(self, path: str, query: dict[str, list[str]]) -> None:
            if path == "/api/meta":
                self._send_json(make_meta_payload(db_path, price_snapshot_path))
                return

            if path == "/api/price":
                symbol = _first(query, "symbol")
                if not symbol:
                    self._send_json({"error": "symbol is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(make_price_payload(symbol, price_snapshot_path))
                return

            if path == "/api/latest":
                sort_by = _first(query, "sort_by") or "symbol"
                sort_order = _first(query, "sort_order") or "asc"
                limit = parse_positive_int(_first(query, "limit"), 100, maximum=5000)
                rows = fetch_latest_pivot(
                    db_path=db_path,
                    symbol=_first(query, "symbol"),
                    limit=5000 if sort_by in PRICE_SORT_FIELDS else limit,
                    sort_by="symbol" if sort_by in PRICE_SORT_FIELDS else sort_by,
                    sort_order=sort_order,
                    min_position_qty=_parse_float(_first(query, "min_position_qty")),
                )
                rows = enrich_latest_rows_with_prices(rows, price_snapshot_path)
                if sort_by in PRICE_SORT_FIELDS:
                    rows = sort_rows(rows, sort_by, sort_order)[:limit]
                self._send_json({"rows": rows, "latest_ts": fetch_latest_ts(db_path=db_path)})
                return

            if path == "/api/history":
                symbol = _first(query, "symbol")
                if not symbol:
                    self._send_json({"error": "symbol is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                rows = fetch_snapshots(
                    db_path=db_path,
                    symbol=symbol,
                    limit=parse_positive_int(_first(query, "limit"), 80, maximum=1000),
                )
                self._send_json({"rows": rows})
                return

            if path == "/api/history-series":
                symbol = _first(query, "symbol")
                if not symbol:
                    self._send_json({"error": "symbol is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                rows = fetch_symbol_timeseries(
                    db_path=db_path,
                    symbol=symbol,
                    limit=parse_positive_int(_first(query, "limit"), 60, maximum=1000),
                )
                self._send_json({"rows": rows})
                return

            if path == "/api/snapshots":
                rows = fetch_snapshots(
                    db_path=db_path,
                    ts_utc=_first(query, "ts_utc"),
                    symbol=_first(query, "symbol"),
                    cohort=_first(query, "cohort"),
                    side=_first(query, "side"),
                    limit=parse_positive_int(_first(query, "limit"), 100, maximum=1000),
                )
                self._send_json({"rows": rows})
                return

            self._send_json({"error": f"unknown endpoint: {path}"}, status=HTTPStatus.NOT_FOUND)

        def _serve_static(self, relative_path: str) -> None:
            target = (FRONTEND_DIR / relative_path).resolve()
            if not str(target).startswith(str(FRONTEND_DIR.resolve())) or not target.exists() or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                return

            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _parse_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the Smart Signal dashboard and JSON API.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--price-snapshot-path", default=str(DEFAULT_PRICE_SNAPSHOT_PATH), help="JSON file path for the latest websocket price snapshot.")
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for rotating log files.")
    parser.add_argument("--log-filename", default="web.log", help="Web server log filename.")
    parser.add_argument("--log-backup-count", type=int, default=DEFAULT_LOG_BACKUP_COUNT, help="Number of rotated log files to keep.")
    return parser.parse_args()


def create_server(*, host: str, port: int, db_path: Path, price_snapshot_path: Path = DEFAULT_PRICE_SNAPSHOT_PATH) -> ThreadingHTTPServer:
    handler = make_handler(db_path, price_snapshot_path)
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    try:
        args = parse_args()
        configure_logging(
            log_level=args.log_level,
            log_dir=args.log_dir,
            log_filename=args.log_filename,
            backup_count=args.log_backup_count,
        )
        install_exception_logging(__name__)
        db_path = Path(args.db_path)
        server = create_server(
            host=args.host,
            port=args.port,
            db_path=db_path,
            price_snapshot_path=Path(args.price_snapshot_path),
        )
        print(f"Smart Signal dashboard serving on http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except KeyboardInterrupt:
        raise
    except Exception:
        LOGGER.exception("web entrypoint crashed")
        raise


if __name__ == "__main__":
    main()
