// Package pricestream provides a WebSocket client for Binance Futures ticker
// stream, persisting latest prices to a JSON file.
package pricestream

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"

	"github.com/btwiuse/BNSmartMoneyMonitor/cli/internal/parser"
)

const (
	// DefaultWSURL is the Binance Futures all-market ticker WebSocket URL.
	DefaultWSURL = "wss://fstream.binance.com/ws/!ticker@arr"
	// DefaultSnapshotPath is the default JSON snapshot file path.
	DefaultSnapshotPath = "data/futures_price_snapshot.json"
	// DefaultFlushSeconds is how often to write the snapshot file.
	DefaultFlushSeconds = 2.0
	// DefaultReconnectSeconds is the automatic reconnect interval (23h).
	DefaultReconnectSeconds = 23 * 60 * 60
)

// PriceEntry holds a single symbol's latest price.
type PriceEntry struct {
	LastPrice   *float64 `json:"last_price"`
	EventTimeMs *int64   `json:"event_time_ms,omitempty"`
}

// Snapshot represents the JSON price snapshot file structure.
type Snapshot struct {
	AsOf         string                `json:"as_of"`
	Source       string                `json:"source"`
	SymbolCount  int                   `json:"symbol_count"`
	Prices       map[string]PriceEntry `json:"prices"`
}

// LoadSnapshot reads an existing snapshot or returns an empty one.
func LoadSnapshot(path string) (*Snapshot, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return &Snapshot{
				Source: DefaultWSURL,
				Prices: make(map[string]PriceEntry),
			}, nil
		}
		return nil, fmt.Errorf("read snapshot: %w", err)
	}

	var snap Snapshot
	if err := json.Unmarshal(data, &snap); err != nil {
		return nil, fmt.Errorf("parse snapshot: %w", err)
	}
	if snap.Prices == nil {
		snap.Prices = make(map[string]PriceEntry)
	}
	snap.SymbolCount = len(snap.Prices)
	return &snap, nil
}

// SaveSnapshot writes prices to the JSON file atomically.
func SaveSnapshot(prices map[string]PriceEntry, path string) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("create directory: %w", err)
	}

	snap := Snapshot{
		AsOf:        time.Now().UTC().Format("2006-01-02T15:04:05.000Z"),
		Source:      DefaultWSURL,
		SymbolCount: len(prices),
		Prices:      prices,
	}

	data, err := json.Marshal(snap)
	if err != nil {
		return err
	}

	tmpPath := path + ".tmp"
	if err := os.WriteFile(tmpPath, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmpPath, path)
}

// ApplyTickerUpdates processes a WebSocket ticker message and updates the prices map.
func ApplyTickerUpdates(prices map[string]PriceEntry, payload []interface{}) int {
	updated := 0
	for _, item := range payload {
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		symbol, _ := m["s"].(string)
		if symbol == "" {
			continue
		}
		lastPrice := parser.NormalizeNumber(m["c"])
		if lastPrice == nil {
			continue
		}

		var eventTime *int64
		if e, ok := m["E"].(float64); ok {
			et := int64(e)
			eventTime = &et
		}

		prices[strings.ToUpper(symbol)] = PriceEntry{
			LastPrice:   lastPrice,
			EventTimeMs: eventTime,
		}
		updated++
	}
	return updated
}

// Run starts the price stream WebSocket client. It reconnects automatically
// on disconnection and flushes prices to a JSON file periodically.
func Run(ctx context.Context, snapshotPath string, flushSeconds float64) error {
	snap, err := LoadSnapshot(snapshotPath)
	if err != nil {
		log.Printf("warning: failed to load snapshot: %v", err)
		snap = &Snapshot{
			Source: DefaultWSURL,
			Prices: make(map[string]PriceEntry),
		}
	}

	mu := sync.Mutex{}
	prices := snap.Prices

	for {
		select {
		case <-ctx.Done():
			mu.Lock()
			_ = SaveSnapshot(prices, snapshotPath)
			mu.Unlock()
			return nil
		default:
		}

		err := runConnection(ctx, &mu, prices, snapshotPath, flushSeconds)
		if err != nil {
			if ctx.Err() != nil {
				mu.Lock()
				_ = SaveSnapshot(prices, snapshotPath)
				mu.Unlock()
				return nil
			}
			log.Printf("price stream disconnected: %v; retrying in 5s", err)
			select {
			case <-ctx.Done():
				mu.Lock()
				_ = SaveSnapshot(prices, snapshotPath)
				mu.Unlock()
				return nil
			case <-time.After(5 * time.Second):
			}
		}
	}
}

func runConnection(ctx context.Context, mu *sync.Mutex, prices map[string]PriceEntry, snapshotPath string, flushSeconds float64) error {
	dialer := websocket.Dialer{
		HandshakeTimeout: 30 * time.Second,
	}
	conn, _, err := dialer.DialContext(ctx, DefaultWSURL, nil)
	if err != nil {
		return fmt.Errorf("connect: %w", err)
	}
	defer conn.Close()

	log.Printf("connected to price stream %s", DefaultWSURL)
	startedAt := time.Now()
	lastFlush := time.Time{}
	flushInterval := time.Duration(flushSeconds * float64(time.Second))

	for {
		select {
		case <-ctx.Done():
			return nil
		default:
		}

		if time.Since(startedAt) >= time.Duration(DefaultReconnectSeconds)*time.Second {
			log.Printf("price stream reconnecting before 24h session limit")
			return nil
		}

		conn.SetReadDeadline(time.Now().Add(2 * time.Second))
		_, msg, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsCloseError(err, websocket.CloseNormalClosure) {
				return nil
			}
			if ctx.Err() != nil {
				return nil
			}
			// Check if it's a timeout - just flush and continue
			if isTimeout(err) {
				mu.Lock()
				if time.Since(lastFlush) >= flushInterval {
					_ = SaveSnapshot(prices, snapshotPath)
					lastFlush = time.Now()
				}
				mu.Unlock()
				continue
			}
			return err
		}

		var payload []interface{}
		if err := json.Unmarshal(msg, &payload); err != nil {
			continue
		}

		mu.Lock()
		updated := ApplyTickerUpdates(prices, payload)
		if updated > 0 && time.Since(lastFlush) >= flushInterval {
			_ = SaveSnapshot(prices, snapshotPath)
			lastFlush = time.Now()
		}
		mu.Unlock()
	}
}

func isTimeout(err error) bool {
	if err == nil {
		return false
	}
	// net.Error interface check
	type netError interface {
		Timeout() bool
	}
	if ne, ok := err.(netError); ok {
		return ne.Timeout()
	}
	return false
}
