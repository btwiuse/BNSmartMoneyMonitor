# Whale Position Research Progress

## 2026-03-10 Step 1

Status: completed

Completed:

- Created a dedicated research task document.
- Split research tracking from the main engineering task log.
- Fixed the initial research scope to `BTCUSDT` at 5-minute frequency.
- Defined the first analysis target set: `5m`, `15m`, `1h`, `4h` future returns.

Next:

- Audit currently available data and identify the exact price-history path for research dataset construction.

## 2026-03-10 Step 2

Status: completed

Completed:

- Audited the local SQLite snapshot table and websocket price snapshot file.
- Confirmed `smart_signal_snapshot` currently spans `2026-03-04T02:35:00Z` to `2026-03-10T02:35:00Z`.
- Confirmed total table size is `647,752` rows across `543` distinct symbols and `312` distinct time buckets.
- Confirmed `BTCUSDT` has `301` distinct 5-minute buckets, which is enough for the first-stage single-symbol study.
- Confirmed the latest production buckets mostly cover `541` symbols per timestamp.
- Confirmed the websocket price file `data/futures_price_snapshot.json` only stores the latest market snapshot and is not a historical time series.
- Confirmed the websocket price snapshot currently has `600` price entries, but only for the latest timestamp, so it cannot be used to compute historical future returns.
- Identified missing-data pressure:
- `position_qty is null`: `14,524` rows
- `avg_entry_price is null`: `752` rows

Research conclusion from this audit:

- Smart Money positioning history is already sufficient to build factor features.
- Historical price series is currently the blocking dependency for return-target construction.
- The next step must add a reproducible price-history source before building the research dataset.

Canonical research dataset shape fixed:

- key: `ts_utc`, `symbol`
- features: whale/trader qty, ratios, net positioning, and change rates
- targets: `5m`, `15m`, `1h`, `4h` future returns
- optional controls: realized volatility and volume

Next:

- Add a research data builder and backfill historical price candles for `BTCUSDT`.

## 2026-03-10 Research Prereq A

Status: completed

Completed:

- Added SQLite price persistence for websocket market prices before entering research Step 3.
- Introduced `futures_price_snapshot` as a dedicated database table keyed by `ts_utc` and `symbol`.
- Wired `collector` to persist the current websocket price snapshot into SQLite at each 5-minute collection bucket.
- Kept the storage cadence aligned with the Smart Money collector, which makes future joins on `ts_utc + symbol` straightforward.
- Added automated tests for price-row mapping, price upsert behavior, and scheduler argument propagation.

Implementation consequence:

- Future research data building can use a single SQLite database for both Smart Money features and synchronized per-bucket prices.
- Historical returns still need time to accumulate from this point onward, but the persistence path is now in place.

Next:

- Let the system accumulate price history in `futures_price_snapshot`.
- Then enter research Step 3 and build the first `BTCUSDT` feature dataset from SQLite.
