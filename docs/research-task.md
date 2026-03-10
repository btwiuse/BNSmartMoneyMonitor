# Whale Position Research Task

## Goal

Build a research workflow to study the relationship between price behavior and whale long/short positioning using the accumulated Smart Money dataset.

Primary questions:

- Do whale position levels lead future returns?
- Do whale position changes lead future returns?
- Does whale/trader divergence contain predictive information?
- Are these effects stable across symbols and horizons?

## Scope

Initial scope:

- Start with `BTCUSDT`
- Use 5-minute buckets
- Focus on whale `qty`, whale long/short ratio, whale net position, and their changes
- Study future returns at `5m`, `15m`, `1h`, `4h`

Expansion scope:

- Extend to `ETHUSDT`
- Extend to full-market panel data
- Add regime filters such as volatility buckets and volume buckets

## Step List

### Step 1

- Create research task and progress documents.
- Define research question, initial scope, and execution order.

### Step 2

- Audit currently available local data sources.
- Confirm which price history fields are already available and which must be added.
- Decide the canonical research dataset schema.

Canonical dataset schema target:

- `ts_utc`
- `symbol`
- `price_close`
- `ret_5m`
- `ret_15m`
- `ret_1h`
- `ret_4h`
- `whale_long_qty`
- `whale_short_qty`
- `whale_long_short_ratio`
- `whale_net_qty`
- `whale_long_qty_change_rate`
- `whale_short_qty_change_rate`
- `trader_long_qty`
- `trader_short_qty`
- `trader_long_short_ratio`
- `trader_net_qty`
- `whale_minus_trader_net_qty`
- optional volatility and volume columns

### Step 3

- Create a reusable research data builder under `research/` or `src/smart_signal/research/`.
- Generate a per-symbol feature table keyed by `ts_utc` and `symbol`.

### Step 4

- Add target columns:
- future returns for `5m`, `15m`, `1h`, `4h`
- optional realized volatility windows

### Step 5

- Add baseline whale features:
- `whale_long_qty`
- `whale_short_qty`
- `whale_long_short_ratio`
- `whale_net_qty`
- `whale_long_qty_change_rate`
- `whale_short_qty_change_rate`

### Step 6

- Add comparative features:
- trader equivalents
- whale minus trader divergence
- lagged features over multiple buckets

### Step 7

- Run descriptive analysis on `BTCUSDT`.
- Produce quantile tables, summary stats, and basic rank correlations.

### Step 8

- Build the first baseline model.
- Start with a simple regression or classification target on future return direction/magnitude.

### Step 9

- Add walk-forward validation.
- Avoid leakage by using only past data in feature construction and scaling.

### Step 10

- Extend from `BTCUSDT` to `ETHUSDT`, then to the full market.
- Compare symbol-specific behavior versus pooled behavior.

## Deliverables

- reproducible feature-building code
- research-ready dataset files
- descriptive analysis output
- baseline modeling script or notebook
- documented conclusions and follow-up hypotheses

## Constraints

- No future leakage
- Keep time alignment explicit
- Treat missing price history as a data engineering blocker, not something to hand-wave
- Prefer simple baselines before complex models
