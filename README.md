# SmartMoney

Binance Futures Smart Money data collector, local dashboard, and SQLite query toolkit.

This project captures Binance Smart Signal market-structure data for `USDT` perpetual contracts and stores it in SQLite for later quant research, signal detection, and monitoring.

## What It Collects

For each symbol and 5-minute bucket:

- `trader` long / short `qty`
- `whale` long / short `qty`
- long / short `avg_entry_price`
- raw response payload for traceability

Current storage table:

- `smart_signal_snapshot`

## Current Architecture

- `collector`: Playwright-based Smart Signal collector
- `scheduler`: long-running 5-minute orchestrator
- `web`: local dashboard and JSON API
- `query`: SQLite query CLI
- `price_stream`: Binance Futures all-market ticker websocket snapshot writer

Notes:

- Smart Money data itself is still collected from Binance page/internal endpoints.
- Market price data is maintained through Binance Futures WebSocket, not repeated REST polling.
- Default full-market symbol resolution uses the committed static list in `config/binance_usdt_perpetual_symbols.txt`.

## Repository Layout

```text
src/smart_signal/      application code
frontend/              dashboard frontend
tests/                 automated tests
config/                static runtime configuration
deploy/                launchd/systemd templates
docs/                  setup and operational docs
```

## Requirements

- Python `3.11+`
- Playwright Chromium
- SQLite

Python dependencies:

- `playwright`
- `websockets`
- `pytest` for development

## Quick Start

### 1. Create and activate a virtualenv

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements-dev.txt
playwright install chromium
```

### 3. Bootstrap Binance login

This creates a persistent Playwright profile under `pw-profile/`.

```bash
PYTHONPATH=src python -m smart_signal.bootstrap_login
```

Log in manually in the browser window, then return to the terminal.

### 4. Run one collection pass

```bash
TMPDIR=$PWD/.tmp PYTHONPATH=src python -m smart_signal.collector --headless
```

### 5. Run the local dashboard

```bash
PYTHONPATH=src python -m smart_signal.web --host 127.0.0.1 --port 8765
```

Open:

- `http://127.0.0.1:8765`

### 6. Run the full scheduler

```bash
TMPDIR=$PWD/.tmp PYTHONPATH=src python -m smart_signal.scheduler
```

This runs:

- the 5-minute collector loop
- the local dashboard
- the Binance Futures ticker websocket stream

## Query Examples

Latest snapshot:

```bash
PYTHONPATH=src python -m smart_signal.query latest --limit 20
```

Single symbol history:

```bash
PYTHONPATH=src python -m smart_signal.query history BTCUSDT --limit 20
```

Raw rows:

```bash
PYTHONPATH=src python -m smart_signal.query snapshots --symbol BTCUSDT --limit 20
```

## Dashboard Features

- latest full-market snapshot table
- single-symbol history panels
- qty time-series chart
- WS latest price display
- filtering and sorting
- auto refresh

## Service Deployment

Template files are included for:

- macOS `launchd`
- Linux `systemd`

See:

- `docs/service.md`

## Tests

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
```

## Security Notes

Do not commit or publish:

- `pw-profile/`
- `data/`
- `logs/`
- `.venv/`
- `.tmp/`

These are already ignored by `.gitignore`, but avoid manually uploading them as well.

`pw-profile/` contains persistent Binance login state and should be treated as sensitive.

## Status

Implemented and verified locally:

- full-market collection using a static `USDT` perpetual symbol list
- SQLite persistence
- dashboard and JSON API
- websocket market-price snapshot service
- long-running scheduler

## License

No license file is included yet. Add one before public distribution if needed.
