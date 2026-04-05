// Package web provides the HTTP dashboard and JSON API server for Smart Signal
// snapshots. It mirrors the Python smart_signal.web module.
package web

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/btwiuse/BNSmartMoneyMonitor/cli/internal/db"
	"github.com/btwiuse/BNSmartMoneyMonitor/cli/internal/pricestream"
)

// ServerConfig holds configuration for the web server.
type ServerConfig struct {
	Host              string
	Port              int
	DBPath            string
	PriceSnapshotPath string
	FrontendDir       string
}

// NewServer creates and returns an HTTP server with all routes configured.
func NewServer(cfg ServerConfig) *http.Server {
	mux := http.NewServeMux()

	mux.HandleFunc("/api/meta", func(w http.ResponseWriter, r *http.Request) {
		handleMeta(w, r, cfg)
	})
	mux.HandleFunc("/api/price", func(w http.ResponseWriter, r *http.Request) {
		handlePrice(w, r, cfg)
	})
	mux.HandleFunc("/api/latest", func(w http.ResponseWriter, r *http.Request) {
		handleLatest(w, r, cfg)
	})
	mux.HandleFunc("/api/history", func(w http.ResponseWriter, r *http.Request) {
		handleHistory(w, r, cfg)
	})
	mux.HandleFunc("/api/history-series", func(w http.ResponseWriter, r *http.Request) {
		handleHistorySeries(w, r, cfg)
	})
	mux.HandleFunc("/api/snapshots", func(w http.ResponseWriter, r *http.Request) {
		handleSnapshots(w, r, cfg)
	})

	// Serve frontend static files
	if cfg.FrontendDir != "" {
		fs := http.FileServer(http.Dir(cfg.FrontendDir))
		mux.Handle("/", fs)
	}

	addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)
	return &http.Server{
		Addr:    addr,
		Handler: mux,
	}
}

func handleMeta(w http.ResponseWriter, _ *http.Request, cfg ServerConfig) {
	database, err := db.Open(cfg.DBPath)
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}
	defer database.Close()

	latestTS, _ := db.FetchLatestTS(database)
	var symbolCount int
	if latestTS != "" {
		rows, _ := db.FetchLatestPivot(database, "", 5000, "symbol", "asc", nil)
		symbolCount = len(rows)
	}

	snap, _ := pricestream.LoadSnapshot(cfg.PriceSnapshotPath)
	payload := map[string]interface{}{
		"latest_ts":              latestTS,
		"symbol_count":          symbolCount,
		"ws_price_as_of":        nil,
		"ws_price_symbol_count": 0,
	}
	if snap != nil {
		if snap.AsOf != "" {
			payload["ws_price_as_of"] = snap.AsOf
		}
		payload["ws_price_symbol_count"] = snap.SymbolCount
	}

	sendJSON(w, http.StatusOK, payload)
}

func handlePrice(w http.ResponseWriter, r *http.Request, cfg ServerConfig) {
	symbol := r.URL.Query().Get("symbol")
	if symbol == "" {
		sendJSON(w, http.StatusBadRequest, map[string]interface{}{"error": "symbol is required"})
		return
	}

	snap, err := pricestream.LoadSnapshot(cfg.PriceSnapshotPath)
	if err != nil {
		sendJSON(w, http.StatusOK, map[string]interface{}{
			"symbol": strings.ToUpper(symbol),
			"last_price": nil,
			"event_time_ms": nil,
			"as_of": nil,
		})
		return
	}

	entry, ok := snap.Prices[strings.ToUpper(symbol)]
	payload := map[string]interface{}{
		"symbol": strings.ToUpper(symbol),
		"last_price": nil,
		"event_time_ms": nil,
		"as_of": snap.AsOf,
	}
	if ok {
		payload["last_price"] = entry.LastPrice
		payload["event_time_ms"] = entry.EventTimeMs
	}
	sendJSON(w, http.StatusOK, payload)
}

func handleLatest(w http.ResponseWriter, r *http.Request, cfg ServerConfig) {
	database, err := db.Open(cfg.DBPath)
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}
	defer database.Close()

	q := r.URL.Query()
	sortBy := queryStr(q, "sort_by", "symbol")
	sortOrder := queryStr(q, "sort_order", "asc")
	limit := queryInt(q, "limit", 100, 1, 5000)
	symbol := q.Get("symbol")
	minQty := queryFloat(q, "min_position_qty")

	rows, err := db.FetchLatestPivot(database, symbol, limit, sortBy, sortOrder, minQty)
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}

	enriched := enrichWithPrices(rows, cfg.PriceSnapshotPath)

	latestTS, _ := db.FetchLatestTS(database)
	sendJSON(w, http.StatusOK, map[string]interface{}{
		"rows":      enriched,
		"latest_ts": latestTS,
	})
}

func handleHistory(w http.ResponseWriter, r *http.Request, cfg ServerConfig) {
	symbol := r.URL.Query().Get("symbol")
	if symbol == "" {
		sendJSON(w, http.StatusBadRequest, map[string]interface{}{"error": "symbol is required"})
		return
	}

	database, err := db.Open(cfg.DBPath)
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}
	defer database.Close()

	limit := queryInt(r.URL.Query(), "limit", 80, 1, 1000)
	rows, err := db.FetchSnapshots(database, db.SnapshotFilter{
		Symbol: symbol,
		Limit:  limit,
	})
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}

	sendJSON(w, http.StatusOK, map[string]interface{}{"rows": snapshotRowsToMaps(rows)})
}

func handleHistorySeries(w http.ResponseWriter, r *http.Request, cfg ServerConfig) {
	symbol := r.URL.Query().Get("symbol")
	if symbol == "" {
		sendJSON(w, http.StatusBadRequest, map[string]interface{}{"error": "symbol is required"})
		return
	}

	database, err := db.Open(cfg.DBPath)
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}
	defer database.Close()

	limit := queryInt(r.URL.Query(), "limit", 60, 1, 1000)
	rows, err := db.FetchSymbolTimeseries(database, symbol, limit)
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}

	sendJSON(w, http.StatusOK, map[string]interface{}{"rows": pivotRowsToMaps(rows)})
}

func handleSnapshots(w http.ResponseWriter, r *http.Request, cfg ServerConfig) {
	database, err := db.Open(cfg.DBPath)
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}
	defer database.Close()

	q := r.URL.Query()
	filter := db.SnapshotFilter{
		TsUTC:  q.Get("ts_utc"),
		Symbol: q.Get("symbol"),
		Cohort: q.Get("cohort"),
		Side:   q.Get("side"),
		Limit:  queryInt(q, "limit", 100, 1, 1000),
	}

	rows, err := db.FetchSnapshots(database, filter)
	if err != nil {
		sendJSON(w, http.StatusInternalServerError, map[string]interface{}{"error": err.Error()})
		return
	}

	sendJSON(w, http.StatusOK, map[string]interface{}{"rows": snapshotRowsToMaps(rows)})
}

func enrichWithPrices(rows []db.PivotRow, snapshotPath string) []map[string]interface{} {
	snap, _ := pricestream.LoadSnapshot(snapshotPath)
	result := make([]map[string]interface{}, 0, len(rows))

	for i := range rows {
		m := db.PivotRowToMap(&rows[i])
		var wsPrice interface{}
		var wsEventTime interface{}
		if snap != nil {
			if entry, ok := snap.Prices[rows[i].Symbol]; ok {
				wsPrice = entry.LastPrice
				wsEventTime = entry.EventTimeMs
			}
		}
		m["ws_last_price"] = wsPrice
		m["ws_price_event_time_ms"] = wsEventTime
		result = append(result, m)
	}
	return result
}

func pivotRowsToMaps(rows []db.PivotRow) []map[string]interface{} {
	result := make([]map[string]interface{}, 0, len(rows))
	for i := range rows {
		result = append(result, db.PivotRowToMap(&rows[i]))
	}
	return result
}

func snapshotRowsToMaps(rows []db.SnapshotRow) []map[string]interface{} {
	result := make([]map[string]interface{}, 0, len(rows))
	for i := range rows {
		result = append(result, db.SnapshotRowToMap(&rows[i]))
	}
	return result
}

func sendJSON(w http.ResponseWriter, status int, payload interface{}) {
	data, err := json.Marshal(payload)
	if err != nil {
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	w.Write(data)
}

func queryStr(q map[string][]string, key, def string) string {
	vals := q[key]
	if len(vals) == 0 || vals[0] == "" {
		return def
	}
	return vals[0]
}

func queryInt(q map[string][]string, key string, def, min, max int) int {
	vals := q[key]
	if len(vals) == 0 || vals[0] == "" {
		return def
	}
	v, err := strconv.Atoi(vals[0])
	if err != nil {
		return def
	}
	if v < min {
		return min
	}
	if v > max {
		return max
	}
	return v
}

func queryFloat(q map[string][]string, key string) *float64 {
	vals := q[key]
	if len(vals) == 0 || vals[0] == "" {
		return nil
	}
	v, err := strconv.ParseFloat(vals[0], 64)
	if err != nil {
		return nil
	}
	return &v
}


