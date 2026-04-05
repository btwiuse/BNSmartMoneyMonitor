// Package cmd implements the CLI commands for the Smart Signal tool.
package cmd

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/btwiuse/BNSmartMoneyMonitor/cli/internal/db"
)

// QueryLatest runs the "query latest" subcommand.
func QueryLatest(dbPath string, symbol string, limit int, format string) error {
	database, err := db.Open(dbPath)
	if err != nil {
		return err
	}
	defer database.Close()

	rows, err := db.FetchLatestPivot(database, symbol, limit, "symbol", "asc", nil)
	if err != nil {
		return err
	}

	maps := make([]map[string]interface{}, len(rows))
	for i := range rows {
		maps[i] = db.PivotRowToMap(&rows[i])
	}
	return emit(maps, format)
}

// QuerySnapshots runs the "query snapshots" subcommand.
func QuerySnapshots(dbPath string, tsUTC string, symbol string, cohort string, side string, limit int, format string) error {
	database, err := db.Open(dbPath)
	if err != nil {
		return err
	}
	defer database.Close()

	if tsUTC == "" {
		ts, err := db.FetchLatestTS(database)
		if err != nil {
			return err
		}
		tsUTC = ts
	}

	rows, err := db.FetchSnapshots(database, db.SnapshotFilter{
		TsUTC:  tsUTC,
		Symbol: symbol,
		Cohort: cohort,
		Side:   side,
		Limit:  limit,
	})
	if err != nil {
		return err
	}

	maps := make([]map[string]interface{}, len(rows))
	for i := range rows {
		maps[i] = db.SnapshotRowToMap(&rows[i])
	}
	return emit(maps, format)
}

// QueryHistory runs the "query history" subcommand.
func QueryHistory(dbPath string, symbol string, limit int, format string) error {
	database, err := db.Open(dbPath)
	if err != nil {
		return err
	}
	defer database.Close()

	rows, err := db.FetchSnapshots(database, db.SnapshotFilter{
		Symbol: symbol,
		Limit:  limit,
	})
	if err != nil {
		return err
	}

	maps := make([]map[string]interface{}, len(rows))
	for i := range rows {
		maps[i] = db.SnapshotRowToMap(&rows[i])
	}
	return emit(maps, format)
}

func emit(rows []map[string]interface{}, format string) error {
	if format == "json" {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(rows)
	}

	if len(rows) == 0 {
		fmt.Println("No rows found.")
		return nil
	}

	fmt.Print(formatTable(rows))
	return nil
}

func formatTable(rows []map[string]interface{}) string {
	if len(rows) == 0 {
		return ""
	}

	// Collect headers from first row
	headers := make([]string, 0)
	for key := range rows[0] {
		if key == "raw_json" {
			continue
		}
		headers = append(headers, key)
	}
	// Sort headers for consistent output
	sortHeaders(headers)

	// Calculate column widths
	widthsInt := make(map[string]int)
	for _, h := range headers {
		widthsInt[h] = len(h)
	}
	for _, row := range rows {
		for _, h := range headers {
			s := stringify(row[h])
			if len(s) > widthsInt[h] {
				widthsInt[h] = len(s)
			}
		}
	}

	var sb strings.Builder
	sep := " | "

	// Header line
	parts := make([]string, len(headers))
	for i, h := range headers {
		parts[i] = padRight(h, widthsInt[h])
	}
	sb.WriteString(strings.Join(parts, sep))
	sb.WriteByte('\n')

	// Separator line
	sepParts := make([]string, len(headers))
	for i, h := range headers {
		sepParts[i] = strings.Repeat("-", widthsInt[h])
	}
	sb.WriteString(strings.Join(sepParts, "-+-"))
	sb.WriteByte('\n')

	// Data lines
	for _, row := range rows {
		for i, h := range headers {
			parts[i] = padRight(stringify(row[h]), widthsInt[h])
		}
		sb.WriteString(strings.Join(parts, sep))
		sb.WriteByte('\n')
	}

	return sb.String()
}

func stringify(v interface{}) string {
	if v == nil {
		return ""
	}
	switch val := v.(type) {
	case *float64:
		if val == nil {
			return ""
		}
		return formatFloat(*val)
	case float64:
		return formatFloat(val)
	case *string:
		if val == nil {
			return ""
		}
		return *val
	default:
		return fmt.Sprintf("%v", v)
	}
}

func formatFloat(f float64) string {
	s := fmt.Sprintf("%.8f", f)
	s = strings.TrimRight(s, "0")
	s = strings.TrimRight(s, ".")
	return s
}

func padRight(s string, width int) string {
	if len(s) >= width {
		return s
	}
	return s + strings.Repeat(" ", width-len(s))
}

func sortHeaders(headers []string) {
	// Prioritize common columns
	priority := map[string]int{
		"ts_utc": 0, "symbol": 1, "cohort": 2, "side": 3,
		"trader_long_qty": 10, "trader_short_qty": 11,
		"whale_long_qty": 12, "whale_short_qty": 13,
		"trader_long_avg_entry_price": 20, "trader_short_avg_entry_price": 21,
		"whale_long_avg_entry_price": 22, "whale_short_avg_entry_price": 23,
		"trader_long_short_ratio": 30, "whale_long_short_ratio": 31,
		"market_long_short_ratio": 32,
		"trader_net_qty": 40, "whale_net_qty": 41,
		"position_qty": 50, "position_usdt": 51, "avg_entry_price": 52,
	}

	for i := 0; i < len(headers); i++ {
		for j := i + 1; j < len(headers); j++ {
			pi, oki := priority[headers[i]]
			pj, okj := priority[headers[j]]
			if !oki {
				pi = 999
			}
			if !okj {
				pj = 999
			}
			if pj < pi || (pi == pj && headers[j] < headers[i]) {
				headers[i], headers[j] = headers[j], headers[i]
			}
		}
	}
}
