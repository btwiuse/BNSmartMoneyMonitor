# Smart Signal Collector Plan

## Stage 1 Scope

- Validate only `BTCUSDT` and `ETHUSDT`.
- Persist both parsed values and source payloads.
- Use 5-minute UTC bucket timestamps.
- Run on Python 3.11+ with Playwright and SQLite.

## Step List

### Step 1

- Establish project skeleton.
- Create `src/smart_signal/` package placeholders and `tests/`.
- Create planning and task-log documents.

### Step 2

- Define configuration constants and runtime layout.
- Decide database path, profile path, retry policy, and initial symbol allowlist.
- Document execution order for bootstrap, collector, and scheduler.

### Step 3

- Implement `src/smart_signal/db.py`.
- Create `smart_signal_snapshot` schema.
- Add idempotent upsert/save helpers.

### Step 4

- Implement `src/smart_signal/parser.py`.
- Support numeric normalization for values such as `951.89M` and `2.41B`.
- Extract long and short position values plus average entry prices.

### Step 5

- Implement `src/smart_signal/binance_symbols.py`.
- Fetch Binance Futures exchange info.
- Filter `PERPETUAL`, `USDT`, `TRADING`.
- Keep first-stage allowlist switch for `BTCUSDT` and `ETHUSDT`.

### Step 6

- Implement `src/smart_signal/bootstrap_login.py`.
- Launch persistent Playwright profile under `./pw-profile`.
- Open Binance Smart Signal and wait for manual login completion.

### Step 7

- Implement `src/smart_signal/collector.py`.
- Visit Smart Signal page per symbol.
- Capture network responses for trader and whale tabs.
- Parse, retry failures, and save raw payloads even on partial parse failure.

### Step 8

- Implement `src/smart_signal/scheduler.py`.
- Run collector every 300 seconds.
- Add logging and failure isolation.
- Support serving the dashboard in the same long-running process.

### Step 9

- Verify on `BTCUSDT` and `ETHUSDT`.
- Promote full-market collection to the default runtime mode.
- Keep `--stage1-only` as a validation fallback.

## Runtime Notes

- Collector should run headless.
- Login bootstrap should run headed.
- Recommended browser concurrency: 3 to 6 pages.
- Prefer cron in production; keep `scheduler.py` as an in-process fallback.
- Add query tooling for inspecting latest snapshots and symbol history from SQLite.
- Add a lightweight browser dashboard for visual inspection of latest market state and symbol history.
