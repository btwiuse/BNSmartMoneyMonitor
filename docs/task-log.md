# Task Log

## 2026-03-04 Step 1

- Established initial project skeleton.
- Created module placeholders: `collector.py`, `parser.py`, `db.py`, `binance_symbols.py`, `scheduler.py`, `bootstrap_login.py`.
- Added planning document in `docs/plan.md`.
- Reserved `docs/task-log.md` as the running implementation log.
- Stage scope fixed to initial validation symbols: `BTCUSDT`, `ETHUSDT`.

## 2026-03-04 Step 2

- Expanded the implementation plan into sequential build steps.
- Locked the first-stage workflow: schema -> parser -> symbol fetch -> login bootstrap -> collector -> scheduler -> validation.
- Documented operational constraints: headless collector, headed bootstrap login, 3 to 6 page concurrency, cron-preferred production mode.

## 2026-03-04 Step 3

- Reworked the repository into a standard source layout.
- Moved runtime modules into `src/smart_signal/`.
- Added `tests/` package placeholder for upcoming parser and database tests.
- Updated planning notes to reference package-based paths instead of root-level modules.

## 2026-03-04 Step 4

- Implemented `src/smart_signal/db.py` with schema initialization, 5-minute UTC bucketing, and SQLite upsert helpers.
- Implemented `src/smart_signal/parser.py` with numeric normalization and generic long/short payload extraction helpers.
- Implemented `src/smart_signal/binance_symbols.py` with Binance Futures exchange info fetch and USDT perpetual symbol filtering.
- Added initial tests for database writes, parser behavior, and symbol filtering.

## 2026-03-04 Step 5

- Added dependency manifests: `requirements.txt` and `requirements-dev.txt`.
- Added `.gitignore` entries for local runtime artifacts such as `.venv/`, `data/`, and `pw-profile/`.
- Added `docs/environment.md` with Python, pip, Playwright, and browser setup instructions.
- Recorded that the current machine only exposes Python `3.9.6`, which is below the project baseline of Python `3.11+`.

## 2026-03-04 Step 6

- Installed Homebrew `python@3.11`.
- Created the project virtual environment at `.venv/`.
- Verified activation resolves `python` and `pip` to `.venv/bin/`.
- Updated environment documentation to reflect the installed interpreter and active virtualenv path.

## 2026-03-04 Step 7

- Installed Python dependencies into `.venv/` from `requirements-dev.txt`.
- Installed Playwright Chromium browser binaries.
- Implemented `src/smart_signal/bootstrap_login.py` for persistent-profile manual Binance login bootstrap.
- Implemented `src/smart_signal/collector.py` with Playwright-based page navigation, network response capture, cohort tab switching, retry handling, and SQLite persistence.
- Added collector-focused unit tests and test path bootstrap in `tests/conftest.py`.

## 2026-03-04 Step 8

- Verified the new implementation under `.venv/`.
- Ran `pytest -q -p no:cacheprovider` with a project-local temporary directory.
- Current automated test result: `10 passed`.

## 2026-03-04 Step 9

- Confirmed Binance page-level "current position (USDT)" is derived from overview quantity times the current page price.
- Reworked collector flow to fetch the `overview` API directly and derive `position_usdt` from quantity and current price.
- Added parser support for overview payloads and quantity-to-USDT conversion.
- Extended tests to cover overview parsing and overview URL generation.

## 2026-03-04 Step 10

- Replaced fragile page-price DOM extraction with Binance ticker API price collection.
- Re-ran the real collector for `BTCUSDT` and `ETHUSDT` using the overview-plus-price path.
- Verified SQLite now stores non-null `position_usdt` and `avg_entry_price` values for trader and whale cohorts.
- Confirmed latest successful snapshot bucket: `2026-03-04T02:50:00Z`.

## 2026-03-04 Step 11

- Switched symbol selection defaults from stage-1 validation mode to full `USDT` perpetual market collection.
- Kept `--stage1-only` as an explicit fallback for targeted validation.
- Added tests covering default full-universe resolution and stage-1 filtering behavior.

## 2026-03-04 Step 12

- Identified the full-market bottleneck as per-symbol ticker requests hitting Binance rate limits.
- Reworked current-price collection to fetch the full ticker book once and reuse it across all symbols.
- Added test coverage for the bulk ticker endpoint helper.

## 2026-03-04 Step 13

- Moved bulk ticker fetching from Playwright page context to direct HTTP for better reliability.
- Re-ran full-market collection over all `USDT` perpetual symbols.
- Successful full-market snapshot completed for `543` symbols at `2026-03-04T03:00:00Z`.
- Runtime benchmark: `131.48s` wall time with `2172` rows written and `0` null-position rows.

## 2026-03-04 Step 14

- Added reusable SQLite query helpers for latest timestamp lookup, filtered raw rows, and pivoted latest snapshots.
- Added `src/smart_signal/query.py` CLI for latest snapshot, raw snapshot, and symbol history queries.
- Added tests covering pivot queries, latest snapshot fallback, and table rendering.

## 2026-03-04 Step 15

- Added a lightweight HTTP dashboard server in `src/smart_signal/web.py`.
- Added frontend assets in `frontend/` for latest snapshot inspection and symbol history browsing.
- Added web-layer tests for basic parameter parsing and meta payload generation.

## 2026-03-04 Step 16

- Added derived fields for latest snapshots and symbol timeseries, including long/short ratios and per-side position change rates.
- Added latest snapshot sorting and minimum-position filtering to the dashboard API.
- Added single-symbol timeseries API and frontend SVG chart rendering for trader/whale long/short positions.
- Added dashboard auto-refresh controls and sorting/filtering UI.

## 2026-03-04 Step 17

- Implemented `src/smart_signal/scheduler.py` as a long-running orchestrator for timed collection cycles.
- Added optional in-process dashboard serving so collection and visualization can run together.
- Added scheduler tests for interval alignment and collector argument mapping.

## 2026-03-04 Step 18

- Added shared rotating file logging in `src/smart_signal/logging_utils.py`.
- Enabled console plus daily rotated log files for scheduler, collector, and web entrypoints.
- Added `logs/` to `.gitignore` and added logging configuration tests.

## 2026-03-04 Step 19

- Updated frontend timestamps to render in Asia/Shanghai (UTC+8).
- Changed single-symbol history cards to use one aggregated row per timestamp bucket with trader/whale positions, ratios, and change rates.
- Fixed chart rendering to use a responsive frame and non-stretched SVG scaling.

## 2026-03-04 Step 20

- Switched bulk ticker fetching to `fapi.binance.com` instead of the web host.
- Added retry with backoff for bulk ticker price fetch failures.
- Hardened `scheduler.py` so a failed collection cycle is logged and the long-running process continues into the next interval.

## 2026-03-04 Step 21

- Added global exception logging hooks for unhandled main-thread and background-thread exceptions.
- Wrapped scheduler, collector, and web entrypoints with top-level `logger.exception(...)` handling.
- Ensured future top-level tracebacks are written into the rotating log files.

## 2026-03-04 Step 22

- Added a ready-to-use macOS `launchd` plist for the current workstation.
- Added a Linux `systemd` unit template for server deployment.
- Documented install, restart, stop, status, and log inspection commands in `docs/service.md`.

## 2026-03-04 Step 23

- Replaced symbol discovery default behavior from exchange-info cache lookup to a committed static full-market symbol list.
- Added `config/binance_usdt_perpetual_symbols.txt` with `541` validated `USDT` perpetual symbols for default runtime use.
- Kept `--refresh-symbols` as an explicit maintenance path that updates the static list file instead of relying on per-run exchange info requests.

## 2026-03-04 Step 24

- Added `src/smart_signal/price_stream.py` to maintain a Binance Futures all-market ticker websocket stream.
- Integrated scheduler startup so the websocket price stream runs alongside the 5-minute collector loop by default.
- Added local snapshot persistence at `data/futures_price_snapshot.json` for future price reuse and reduced REST pressure.

## 2026-03-04 Step 25

- Initialized a local Git repository for publication prep.
- De-personalized service and environment documentation by removing workstation-specific usernames and absolute paths.
- Converted the committed macOS `launchd` service definition into a reusable public template and ignored `.tmp/` runtime artifacts.

## 2026-03-10 Step 26

- Created dedicated research planning and progress documents for whale-position versus price analysis.
- Separated research tracking from the main collector/dashboard engineering log.
- Fixed the first research stage to `BTCUSDT` and explicit future-return horizons.

## 2026-03-10 Step 27

- Audited currently available research inputs in SQLite and the websocket price snapshot.
- Confirmed Smart Money history is sufficient for factor construction, but local websocket price storage is only a latest snapshot and not a historical series.
- Fixed the canonical research dataset shape and identified historical price backfill as the next blocker.

## 2026-03-10 Step 28

- Added SQLite persistence for websocket market prices using a new `futures_price_snapshot` table.
- Wired `collector.py` to save the current websocket price snapshot into the database at each 5-minute bucket before Smart Money collection proceeds.
- Added tests for price snapshot row mapping, price upsert behavior, and scheduler-to-collector argument propagation.
