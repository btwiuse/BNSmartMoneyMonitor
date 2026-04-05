// Package symbols provides Binance Futures symbol discovery and caching.
package symbols

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const (
	// ExchangeInfoURL is the Binance Futures exchange info endpoint.
	ExchangeInfoURL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
	// DefaultSymbolListPath is the default cached symbol list location.
	DefaultSymbolListPath = "config/binance_usdt_perpetual_symbols.txt"
)

// FetchExchangeInfo fetches the Binance Futures exchangeInfo.
func FetchExchangeInfo(timeout time.Duration) (map[string]interface{}, error) {
	client := &http.Client{Timeout: timeout}
	req, err := http.NewRequest("GET", ExchangeInfoURL, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "smart-signal-cli/0.1")

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch exchange info: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	var result map[string]interface{}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse JSON: %w", err)
	}
	return result, nil
}

// FilterUSDTPerpetualSymbols extracts USDT perpetual trading symbols from exchangeInfo.
func FilterUSDTPerpetualSymbols(exchangeInfo map[string]interface{}) []string {
	symbolsRaw, ok := exchangeInfo["symbols"]
	if !ok {
		return nil
	}
	items, ok := symbolsRaw.([]interface{})
	if !ok {
		return nil
	}

	seen := make(map[string]bool)
	var symbols []string
	for _, item := range items {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		contractType, _ := m["contractType"].(string)
		quoteAsset, _ := m["quoteAsset"].(string)
		status, _ := m["status"].(string)
		symbol, _ := m["symbol"].(string)

		if contractType != "PERPETUAL" || quoteAsset != "USDT" || status != "TRADING" || symbol == "" {
			continue
		}
		if !seen[symbol] {
			seen[symbol] = true
			symbols = append(symbols, symbol)
		}
	}
	sort.Strings(symbols)
	return symbols
}

// LoadSymbolList reads symbols from a file (one per line).
func LoadSymbolList(path string) ([]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("read symbol list: %w", err)
	}

	lines := strings.Split(string(data), "\n")
	seen := make(map[string]bool)
	var symbols []string
	for _, line := range lines {
		s := strings.TrimSpace(strings.ToUpper(line))
		if s != "" && !seen[s] {
			seen[s] = true
			symbols = append(symbols, s)
		}
	}
	sort.Strings(symbols)
	return symbols, nil
}

// SaveSymbolList writes symbols to a file (one per line).
func SaveSymbolList(symbols []string, path string) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("create directory: %w", err)
	}

	// Deduplicate and sort
	seen := make(map[string]bool)
	var unique []string
	for _, s := range symbols {
		s = strings.TrimSpace(strings.ToUpper(s))
		if s != "" && !seen[s] {
			seen[s] = true
			unique = append(unique, s)
		}
	}
	sort.Strings(unique)

	content := strings.Join(unique, "\n") + "\n"
	return os.WriteFile(path, []byte(content), 0o644)
}

// GetTargetSymbols resolves the target symbol list using the fallback chain:
// 1. Load from static list (unless refresh=true)
// 2. Fetch from Binance exchangeInfo
// 3. Fall back to static list on network failure
// 4. Apply allowlist if provided
func GetTargetSymbols(listPath string, refresh bool, allowlist []string, stage1Only bool) ([]string, string, error) {
	var symbols []string
	source := listPath

	if !refresh {
		cached, err := LoadSymbolList(listPath)
		if err != nil {
			return nil, "", err
		}
		symbols = cached
	}

	if symbols == nil {
		info, err := FetchExchangeInfo(15 * time.Second)
		if err != nil {
			// Fall back to static list
			fallback, loadErr := LoadSymbolList(listPath)
			if loadErr != nil || fallback == nil {
				return nil, "", fmt.Errorf("fetch exchange info failed (%w) and no cached list available", err)
			}
			symbols = fallback
			source = listPath
		} else {
			symbols = FilterUSDTPerpetualSymbols(info)
			if saveErr := SaveSymbolList(symbols, listPath); saveErr != nil {
				// Log but don't fail
				fmt.Fprintf(os.Stderr, "warning: failed to cache symbol list: %v\n", saveErr)
			}
			source = ExchangeInfoURL
		}
	}

	if stage1Only && len(allowlist) == 0 {
		allowlist = []string{"BTCUSDT", "ETHUSDT"}
	}

	if len(allowlist) > 0 {
		allowed := make(map[string]bool)
		for _, s := range allowlist {
			allowed[strings.ToUpper(s)] = true
		}
		filtered := symbols[:0]
		for _, s := range symbols {
			if allowed[strings.ToUpper(s)] {
				filtered = append(filtered, s)
			}
		}
		symbols = filtered
	}

	return symbols, source, nil
}
