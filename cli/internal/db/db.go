// Package db provides SQLite persistence and query helpers for Smart Signal
// snapshots. It mirrors the Python smart_signal.db module.
package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"path/filepath"
	"os"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

// DefaultDBPath is the default SQLite database location.
const DefaultDBPath = "data/smart_signal.sqlite3"

const schemaDDL = `
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
`

// SnapshotRow represents a row from the smart_signal_snapshot table.
type SnapshotRow struct {
	TsUTC         string   `json:"ts_utc"`
	Symbol        string   `json:"symbol"`
	Cohort        string   `json:"cohort"`
	Side          string   `json:"side"`
	PositionQty   *float64 `json:"position_qty"`
	PositionUSDT  *float64 `json:"position_usdt"`
	AvgEntryPrice *float64 `json:"avg_entry_price"`
	RawJSON       *string  `json:"raw_json,omitempty"`
}

// PivotRow represents a pivoted snapshot row with enriched calculated fields.
type PivotRow struct {
	TsUTC                    string   `json:"ts_utc"`
	Symbol                   string   `json:"symbol"`
	TraderLongQty            *float64 `json:"trader_long_qty"`
	TraderShortQty           *float64 `json:"trader_short_qty"`
	WhaleLongQty             *float64 `json:"whale_long_qty"`
	WhaleShortQty            *float64 `json:"whale_short_qty"`
	TraderLongAvgEntryPrice  *float64 `json:"trader_long_avg_entry_price"`
	TraderShortAvgEntryPrice *float64 `json:"trader_short_avg_entry_price"`
	WhaleLongAvgEntryPrice   *float64 `json:"whale_long_avg_entry_price"`
	WhaleShortAvgEntryPrice  *float64 `json:"whale_short_avg_entry_price"`
	TraderLongShortRatio     *float64 `json:"trader_long_short_ratio"`
	WhaleLongShortRatio      *float64 `json:"whale_long_short_ratio"`
	MarketLongShortRatio     *float64 `json:"market_long_short_ratio"`
	TraderNetQty             *float64 `json:"trader_net_qty"`
	WhaleNetQty              *float64 `json:"whale_net_qty"`
	TraderLongQtyChangeRate  *float64 `json:"trader_long_qty_change_rate"`
	TraderShortQtyChangeRate *float64 `json:"trader_short_qty_change_rate"`
	WhaleLongQtyChangeRate   *float64 `json:"whale_long_qty_change_rate"`
	WhaleShortQtyChangeRate  *float64 `json:"whale_short_qty_change_rate"`
}

// FloorUTCTo5Min returns an ISO8601 UTC timestamp rounded down to the nearest 5 minutes.
func FloorUTCTo5Min(t time.Time) string {
	t = t.UTC()
	floored := time.Date(t.Year(), t.Month(), t.Day(), t.Hour(), (t.Minute()/5)*5, 0, 0, time.UTC)
	return floored.Format("2006-01-02T15:04:05Z")
}

// Open opens or creates the SQLite database at the given path and ensures
// the schema tables exist.
func Open(dbPath string) (*sql.DB, error) {
	dir := filepath.Dir(dbPath)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("create db directory: %w", err)
	}
	database, err := sql.Open("sqlite3", dbPath+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}
	if _, err := database.Exec(schemaDDL); err != nil {
		database.Close()
		return nil, fmt.Errorf("ensure schema: %w", err)
	}
	return database, nil
}

// InitDB creates schema tables if they don't exist.
func InitDB(dbPath string) error {
	db, err := Open(dbPath)
	if err != nil {
		return err
	}
	defer db.Close()
	_, err = db.Exec(schemaDDL)
	if err != nil {
		return fmt.Errorf("create schema: %w", err)
	}
	return nil
}

// FetchLatestTS returns the most recent 5-min bucket timestamp.
func FetchLatestTS(db *sql.DB) (string, error) {
	var ts sql.NullString
	err := db.QueryRow("SELECT MAX(ts_utc) FROM smart_signal_snapshot").Scan(&ts)
	if err != nil {
		return "", err
	}
	if !ts.Valid {
		return "", nil
	}
	return ts.String, nil
}

// FetchPreviousTS returns the most recent timestamp before the given one.
func FetchPreviousTS(db *sql.DB, tsUTC string) (string, error) {
	var ts sql.NullString
	err := db.QueryRow("SELECT MAX(ts_utc) FROM smart_signal_snapshot WHERE ts_utc < ?", tsUTC).Scan(&ts)
	if err != nil {
		return "", err
	}
	if !ts.Valid {
		return "", nil
	}
	return ts.String, nil
}

// FetchDistinctSymbols returns all unique symbols in the database.
func FetchDistinctSymbols(db *sql.DB) ([]string, error) {
	rows, err := db.Query("SELECT DISTINCT symbol FROM smart_signal_snapshot ORDER BY symbol")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var symbols []string
	for rows.Next() {
		var s string
		if err := rows.Scan(&s); err != nil {
			return nil, err
		}
		symbols = append(symbols, s)
	}
	return symbols, rows.Err()
}

// SnapshotFilter holds optional filters for snapshot queries.
type SnapshotFilter struct {
	TsUTC  string
	Symbol string
	Cohort string
	Side   string
	Limit  int
}

// FetchSnapshots fetches raw snapshot rows with optional filters.
func FetchSnapshots(db *sql.DB, f SnapshotFilter) ([]SnapshotRow, error) {
	var clauses []string
	var params []interface{}

	if f.TsUTC != "" {
		clauses = append(clauses, "ts_utc = ?")
		params = append(params, f.TsUTC)
	}
	if f.Symbol != "" {
		clauses = append(clauses, "symbol = ?")
		params = append(params, strings.ToUpper(f.Symbol))
	}
	if f.Cohort != "" {
		clauses = append(clauses, "cohort = ?")
		params = append(params, strings.ToLower(f.Cohort))
	}
	if f.Side != "" {
		clauses = append(clauses, "side = ?")
		params = append(params, strings.ToLower(f.Side))
	}

	query := "SELECT ts_utc, symbol, cohort, side, position_qty, position_usdt, avg_entry_price, raw_json FROM smart_signal_snapshot"
	if len(clauses) > 0 {
		query += " WHERE " + strings.Join(clauses, " AND ")
	}
	query += " ORDER BY ts_utc DESC, symbol, cohort, side"

	limit := f.Limit
	if limit <= 0 {
		limit = 100
	}
	query += fmt.Sprintf(" LIMIT %d", limit)

	rows, err := db.Query(query, params...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []SnapshotRow
	for rows.Next() {
		var r SnapshotRow
		if err := rows.Scan(&r.TsUTC, &r.Symbol, &r.Cohort, &r.Side,
			&r.PositionQty, &r.PositionUSDT, &r.AvgEntryPrice, &r.RawJSON); err != nil {
			return nil, err
		}
		results = append(results, r)
	}
	return results, rows.Err()
}

// FetchPivotByTS returns pivoted snapshot for a specific timestamp.
func FetchPivotByTS(db *sql.DB, tsUTC string, symbol string, limit int) ([]PivotRow, error) {
	if tsUTC == "" {
		return nil, nil
	}
	if limit <= 0 {
		limit = 100
	}

	var params []interface{}
	params = append(params, tsUTC)

	symbolClause := ""
	if symbol != "" {
		symbolClause = " AND symbol = ?"
		params = append(params, strings.ToUpper(symbol))
	}
	params = append(params, limit)

	query := fmt.Sprintf(`
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
	WHERE ts_utc = ? %s
	GROUP BY ts_utc, symbol
	ORDER BY symbol
	LIMIT ?
	`, symbolClause)

	rows, err := db.Query(query, params...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []PivotRow
	for rows.Next() {
		var r PivotRow
		if err := rows.Scan(
			&r.TsUTC, &r.Symbol,
			&r.TraderLongQty, &r.TraderShortQty,
			&r.WhaleLongQty, &r.WhaleShortQty,
			&r.TraderLongAvgEntryPrice, &r.TraderShortAvgEntryPrice,
			&r.WhaleLongAvgEntryPrice, &r.WhaleShortAvgEntryPrice,
		); err != nil {
			return nil, err
		}
		results = append(results, r)
	}
	return results, rows.Err()
}

// EnrichPivotRow calculates derived metrics (ratios, net quantities, change rates).
func EnrichPivotRow(row *PivotRow, prev *PivotRow) {
	row.TraderLongShortRatio = safeDivide(row.TraderLongQty, row.TraderShortQty)
	row.WhaleLongShortRatio = safeDivide(row.WhaleLongQty, row.WhaleShortQty)

	totalLong := ptrOr(row.TraderLongQty, 0) + ptrOr(row.WhaleLongQty, 0)
	totalShort := ptrOr(row.TraderShortQty, 0) + ptrOr(row.WhaleShortQty, 0)
	row.MarketLongShortRatio = safeDivideVal(totalLong, totalShort)

	traderNet := ptrOr(row.TraderLongQty, 0) - ptrOr(row.TraderShortQty, 0)
	whaleNet := ptrOr(row.WhaleLongQty, 0) - ptrOr(row.WhaleShortQty, 0)
	row.TraderNetQty = &traderNet
	row.WhaleNetQty = &whaleNet

	if prev != nil {
		row.TraderLongQtyChangeRate = changeRate(row.TraderLongQty, prev.TraderLongQty)
		row.TraderShortQtyChangeRate = changeRate(row.TraderShortQty, prev.TraderShortQty)
		row.WhaleLongQtyChangeRate = changeRate(row.WhaleLongQty, prev.WhaleLongQty)
		row.WhaleShortQtyChangeRate = changeRate(row.WhaleShortQty, prev.WhaleShortQty)
	}
}

// FetchLatestPivot returns the most recent snapshot pivoted by symbol with enrichment.
func FetchLatestPivot(db *sql.DB, symbol string, limit int, sortBy string, sortOrder string, minPositionQty *float64) ([]PivotRow, error) {
	latestTS, err := FetchLatestTS(db)
	if err != nil || latestTS == "" {
		return nil, err
	}

	previousTS, err := FetchPreviousTS(db, latestTS)
	if err != nil {
		return nil, err
	}

	latestRows, err := FetchPivotByTS(db, latestTS, symbol, 5000)
	if err != nil {
		return nil, err
	}

	var prevBySymbol map[string]*PivotRow
	if previousTS != "" {
		prevRows, err := FetchPivotByTS(db, previousTS, symbol, 5000)
		if err != nil {
			return nil, err
		}
		prevBySymbol = make(map[string]*PivotRow, len(prevRows))
		for i := range prevRows {
			prevBySymbol[prevRows[i].Symbol] = &prevRows[i]
		}
	}

	for i := range latestRows {
		var prev *PivotRow
		if prevBySymbol != nil {
			prev = prevBySymbol[latestRows[i].Symbol]
		}
		EnrichPivotRow(&latestRows[i], prev)
	}

	// Filter by min position qty
	if minPositionQty != nil {
		filtered := latestRows[:0]
		for _, r := range latestRows {
			maxQty := maxOf(
				ptrOr(r.TraderLongQty, 0),
				ptrOr(r.TraderShortQty, 0),
				ptrOr(r.WhaleLongQty, 0),
				ptrOr(r.WhaleShortQty, 0),
			)
			if maxQty >= *minPositionQty {
				filtered = append(filtered, r)
			}
		}
		latestRows = filtered
	}

	// Sort (only symbol sort implemented for simplicity in the DB layer)
	if limit <= 0 {
		limit = 100
	}
	if len(latestRows) > limit {
		latestRows = latestRows[:limit]
	}

	return latestRows, nil
}

// FetchSymbolTimeseries returns time-series data for a symbol.
func FetchSymbolTimeseries(db *sql.DB, symbol string, limit int) ([]PivotRow, error) {
	if limit <= 0 {
		limit = 120
	}

	query := `
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
	`

	rows, err := db.Query(query, strings.ToUpper(symbol), limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var descending []PivotRow
	for rows.Next() {
		var r PivotRow
		if err := rows.Scan(
			&r.TsUTC, &r.Symbol,
			&r.TraderLongQty, &r.TraderShortQty,
			&r.WhaleLongQty, &r.WhaleShortQty,
			&r.TraderLongAvgEntryPrice, &r.TraderShortAvgEntryPrice,
			&r.WhaleLongAvgEntryPrice, &r.WhaleShortAvgEntryPrice,
		); err != nil {
			return nil, err
		}
		descending = append(descending, r)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	// Reverse to oldest-first
	for i, j := 0, len(descending)-1; i < j; i, j = i+1, j-1 {
		descending[i], descending[j] = descending[j], descending[i]
	}

	// Enrich with change rates
	var prev *PivotRow
	for i := range descending {
		EnrichPivotRow(&descending[i], prev)
		prev = &descending[i]
	}

	return descending, nil
}

// PivotRowToMap converts a PivotRow to a map for JSON serialization.
func PivotRowToMap(r *PivotRow) map[string]interface{} {
	m := make(map[string]interface{})
	m["ts_utc"] = r.TsUTC
	m["symbol"] = r.Symbol
	m["trader_long_qty"] = r.TraderLongQty
	m["trader_short_qty"] = r.TraderShortQty
	m["whale_long_qty"] = r.WhaleLongQty
	m["whale_short_qty"] = r.WhaleShortQty
	m["trader_long_avg_entry_price"] = r.TraderLongAvgEntryPrice
	m["trader_short_avg_entry_price"] = r.TraderShortAvgEntryPrice
	m["whale_long_avg_entry_price"] = r.WhaleLongAvgEntryPrice
	m["whale_short_avg_entry_price"] = r.WhaleShortAvgEntryPrice
	m["trader_long_short_ratio"] = r.TraderLongShortRatio
	m["whale_long_short_ratio"] = r.WhaleLongShortRatio
	m["market_long_short_ratio"] = r.MarketLongShortRatio
	m["trader_net_qty"] = r.TraderNetQty
	m["whale_net_qty"] = r.WhaleNetQty
	m["trader_long_qty_change_rate"] = r.TraderLongQtyChangeRate
	m["trader_short_qty_change_rate"] = r.TraderShortQtyChangeRate
	m["whale_long_qty_change_rate"] = r.WhaleLongQtyChangeRate
	m["whale_short_qty_change_rate"] = r.WhaleShortQtyChangeRate
	return m
}

// SnapshotRowToMap converts a SnapshotRow to a map for JSON serialization.
func SnapshotRowToMap(r *SnapshotRow) map[string]interface{} {
	m := make(map[string]interface{})
	m["ts_utc"] = r.TsUTC
	m["symbol"] = r.Symbol
	m["cohort"] = r.Cohort
	m["side"] = r.Side
	m["position_qty"] = r.PositionQty
	m["position_usdt"] = r.PositionUSDT
	m["avg_entry_price"] = r.AvgEntryPrice
	if r.RawJSON != nil {
		m["raw_json"] = json.RawMessage(*r.RawJSON)
	}
	return m
}

func safeDivide(num, denom *float64) *float64 {
	if num == nil || denom == nil || *denom == 0 {
		return nil
	}
	r := *num / *denom
	return &r
}

func safeDivideVal(num, denom float64) *float64 {
	if denom == 0 {
		return nil
	}
	r := num / denom
	return &r
}

func changeRate(current, previous *float64) *float64 {
	if current == nil || previous == nil || *previous == 0 {
		return nil
	}
	r := (*current - *previous) / *previous
	return &r
}

func ptrOr(p *float64, def float64) float64 {
	if p == nil {
		return def
	}
	return *p
}

func maxOf(vals ...float64) float64 {
	m := vals[0]
	for _, v := range vals[1:] {
		if v > m {
			m = v
		}
	}
	return m
}
