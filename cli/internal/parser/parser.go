// Package parser provides number normalization and signal parsing for Binance
// Smart Signal payloads. It mirrors the Python smart_signal.parser module.
package parser

import (
	"math"
	"regexp"
	"strings"
)

var numericTokenRE = regexp.MustCompile(`(?i)^\s*([+-]?\d+(?:\.\d+)?)\s*([KMBT]?)\s*$`)

var multipliers = map[string]float64{
	"":  1,
	"K": 1_000,
	"M": 1_000_000,
	"B": 1_000_000_000,
	"T": 1_000_000_000_000,
}

// NormalizeNumber parses Binance UI numeric strings such as "951.89M" or "2.41B".
// Returns nil when the value cannot be parsed.
func NormalizeNumber(value interface{}) *float64 {
	switch v := value.(type) {
	case nil:
		return nil
	case bool:
		return nil
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return nil
		}
		return &v
	case float32:
		f := float64(v)
		return &f
	case int:
		f := float64(v)
		return &f
	case int64:
		f := float64(v)
		return &f
	case string:
		return parseNumericString(v)
	default:
		return nil
	}
}

func parseNumericString(text string) *float64 {
	text = strings.TrimSpace(text)
	if text == "" || text == "--" || text == "N/A" || text == "null" || text == "None" {
		return nil
	}

	compact := strings.ReplaceAll(text, ",", "")
	compact = strings.ReplaceAll(compact, "$", "")
	compact = strings.ReplaceAll(compact, "USDT", "")
	compact = strings.ReplaceAll(compact, "USD", "")
	compact = strings.TrimSpace(compact)

	matches := numericTokenRE.FindStringSubmatch(compact)
	if matches == nil {
		return nil
	}

	number := 0.0
	_, err := parseFloat(matches[1], &number)
	if err {
		return nil
	}

	suffix := strings.ToUpper(matches[2])
	mult, ok := multipliers[suffix]
	if !ok {
		return nil
	}

	result := number * mult
	return &result
}

func parseFloat(s string, out *float64) (int, bool) {
	// simple float parser
	var f float64
	n, err := scanFloat(s, &f)
	if err {
		return 0, true
	}
	*out = f
	return n, false
}

func scanFloat(s string, out *float64) (int, bool) {
	if s == "" {
		return 0, true
	}
	negative := false
	i := 0
	if s[0] == '+' {
		i++
	} else if s[0] == '-' {
		negative = true
		i++
	}

	var intPart float64
	hasDigits := false
	for i < len(s) && s[i] >= '0' && s[i] <= '9' {
		intPart = intPart*10 + float64(s[i]-'0')
		hasDigits = true
		i++
	}

	var fracPart float64
	if i < len(s) && s[i] == '.' {
		i++
		divisor := 10.0
		for i < len(s) && s[i] >= '0' && s[i] <= '9' {
			fracPart += float64(s[i]-'0') / divisor
			divisor *= 10
			hasDigits = true
			i++
		}
	}

	if !hasDigits {
		return 0, true
	}

	result := intPart + fracPart
	if negative {
		result = -result
	}
	*out = result
	return i, false
}

// SideSnapshot holds parsed data for one side (long or short).
type SideSnapshot struct {
	Side         string   `json:"side"`
	PositionQty  *float64 `json:"position_qty"`
	PositionUSDT *float64 `json:"position_usdt"`
	AvgEntryPrice *float64 `json:"avg_entry_price"`
}

// ParsedSignal holds parsed long and short data.
type ParsedSignal struct {
	Long  SideSnapshot `json:"long"`
	Short SideSnapshot `json:"short"`
}

// ParseOverviewPayload parses a Binance Smart Signal overview API response
// for a given cohort ("trader" or "whale").
func ParseOverviewPayload(payload map[string]interface{}, cohort string) *ParsedSignal {
	data, ok := payload["data"]
	if !ok {
		data = payload
	}
	dataMap, ok := data.(map[string]interface{})
	if !ok {
		return nil
	}

	prefix := "Traders"
	if cohort != "trader" {
		prefix = "Whales"
	}

	longQtyKey := "long" + prefix + "Qty"
	shortQtyKey := "short" + prefix + "Qty"
	longAvgKey := "long" + prefix + "AvgEntryPrice"
	shortAvgKey := "short" + prefix + "AvgEntryPrice"

	_, hasLong := dataMap[longQtyKey]
	_, hasShort := dataMap[shortQtyKey]
	if !hasLong && !hasShort {
		return nil
	}

	return &ParsedSignal{
		Long: SideSnapshot{
			Side:         "long",
			PositionQty:  NormalizeNumber(dataMap[longQtyKey]),
			AvgEntryPrice: NormalizeNumber(dataMap[longAvgKey]),
		},
		Short: SideSnapshot{
			Side:         "short",
			PositionQty:  NormalizeNumber(dataMap[shortQtyKey]),
			AvgEntryPrice: NormalizeNumber(dataMap[shortAvgKey]),
		},
	}
}
