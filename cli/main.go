// smart-signal is a CLI tool for querying, serving, and streaming Binance
// Smart Signal data. It provides the core backend functionality of
// BNSmartMoneyMonitor as a standalone Go binary.
//
// Usage:
//
//	smart-signal <command> [flags]
//
// Commands:
//
//	query       Query Smart Signal snapshots from SQLite
//	serve       Start the dashboard web server and JSON API
//	stream      Run Binance Futures price WebSocket stream
//	symbols     List or refresh Binance USDT perpetual symbols
//	version     Print version information
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/btwiuse/BNSmartMoneyMonitor/cli/cmd"
	"github.com/btwiuse/BNSmartMoneyMonitor/cli/internal/db"
	"github.com/btwiuse/BNSmartMoneyMonitor/cli/internal/pricestream"
	"github.com/btwiuse/BNSmartMoneyMonitor/cli/internal/symbols"
	"github.com/btwiuse/BNSmartMoneyMonitor/cli/internal/web"
)

var version = "dev"

func main() {
	log.SetFlags(log.LstdFlags | log.Lmsgprefix)
	log.SetPrefix("[smart-signal] ")

	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	command := os.Args[1]
	switch command {
	case "query":
		runQuery(os.Args[2:])
	case "serve":
		runServe(os.Args[2:])
	case "stream":
		runStream(os.Args[2:])
	case "symbols":
		runSymbols(os.Args[2:])
	case "version":
		fmt.Printf("smart-signal %s\n", version)
	case "help", "-h", "--help":
		printUsage()
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n\n", command)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Fprintf(os.Stderr, `smart-signal - Binance Smart Signal CLI

Usage:
  smart-signal <command> [flags]

Commands:
  query       Query Smart Signal snapshots from SQLite
  serve       Start the dashboard web server and JSON API
  stream      Run Binance Futures price WebSocket stream
  symbols     List or refresh Binance USDT perpetual symbols
  version     Print version information

Run 'smart-signal <command> -h' for details on each command.
`)
}

// ---------- query ----------

func runQuery(args []string) {
	if len(args) == 0 || args[0] == "-h" || args[0] == "--help" {
		fmt.Fprintf(os.Stderr, `Usage: smart-signal query <subcommand> [flags]

Subcommands:
  latest      Show latest snapshot pivoted by symbol
  snapshots   Show raw snapshot rows
  history     Show historical rows for one symbol

`)
		os.Exit(1)
	}

	subcmd := args[0]
	subArgs := args[1:]

	switch subcmd {
	case "latest":
		runQueryLatest(subArgs)
	case "snapshots":
		runQuerySnapshots(subArgs)
	case "history":
		runQueryHistory(subArgs)
	default:
		fmt.Fprintf(os.Stderr, "unknown query subcommand: %s\n", subcmd)
		os.Exit(1)
	}
}

func runQueryLatest(args []string) {
	fs := flag.NewFlagSet("query latest", flag.ExitOnError)
	dbPath := fs.String("db-path", db.DefaultDBPath, "SQLite database path")
	symbol := fs.String("symbol", "", "Restrict to a single symbol")
	limit := fs.Int("limit", 20, "Maximum number of symbols to return")
	format := fs.String("format", "table", "Output format: table or json")
	fs.Parse(args)

	if err := cmd.QueryLatest(*dbPath, *symbol, *limit, *format); err != nil {
		log.Fatal(err)
	}
}

func runQuerySnapshots(args []string) {
	fs := flag.NewFlagSet("query snapshots", flag.ExitOnError)
	dbPath := fs.String("db-path", db.DefaultDBPath, "SQLite database path")
	tsUTC := fs.String("ts-utc", "", "Exact UTC bucket timestamp")
	symbol := fs.String("symbol", "", "Restrict to a single symbol")
	cohort := fs.String("cohort", "", "Filter by cohort: trader or whale")
	side := fs.String("side", "", "Filter by side: long or short")
	limit := fs.Int("limit", 50, "Maximum number of rows to return")
	format := fs.String("format", "table", "Output format: table or json")
	fs.Parse(args)

	if err := cmd.QuerySnapshots(*dbPath, *tsUTC, *symbol, *cohort, *side, *limit, *format); err != nil {
		log.Fatal(err)
	}
}

func runQueryHistory(args []string) {
	fs := flag.NewFlagSet("query history", flag.ExitOnError)
	dbPath := fs.String("db-path", db.DefaultDBPath, "SQLite database path")
	limit := fs.Int("limit", 40, "Maximum number of rows to return")
	format := fs.String("format", "table", "Output format: table or json")
	fs.Parse(args)

	remaining := fs.Args()
	if len(remaining) == 0 {
		fmt.Fprintf(os.Stderr, "Usage: smart-signal query history <SYMBOL> [flags]\n")
		os.Exit(1)
	}
	symbol := strings.ToUpper(remaining[0])

	if err := cmd.QueryHistory(*dbPath, symbol, *limit, *format); err != nil {
		log.Fatal(err)
	}
}

// ---------- serve ----------

func runServe(args []string) {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	host := fs.String("host", "127.0.0.1", "Bind host")
	port := fs.Int("port", 8765, "Bind port")
	dbPath := fs.String("db-path", db.DefaultDBPath, "SQLite database path")
	priceSnapshotPath := fs.String("price-snapshot-path", pricestream.DefaultSnapshotPath, "JSON price snapshot path")
	frontendDir := fs.String("frontend-dir", findFrontendDir(), "Frontend static files directory")
	fs.Parse(args)

	cfg := web.ServerConfig{
		Host:              *host,
		Port:              *port,
		DBPath:            *dbPath,
		PriceSnapshotPath: *priceSnapshotPath,
		FrontendDir:       *frontendDir,
	}

	server := web.NewServer(cfg)
	fmt.Printf("Smart Signal dashboard serving on http://%s:%d\n", *host, *port)

	// Handle graceful shutdown
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	go func() {
		<-ctx.Done()
		log.Println("shutting down server...")
		server.Close()
	}()

	if err := server.ListenAndServe(); err != nil && err.Error() != "http: Server closed" {
		log.Fatal(err)
	}
}

// ---------- stream ----------

func runStream(args []string) {
	fs := flag.NewFlagSet("stream", flag.ExitOnError)
	snapshotPath := fs.String("snapshot-path", pricestream.DefaultSnapshotPath, "JSON price snapshot path")
	flushSeconds := fs.Float64("flush-seconds", pricestream.DefaultFlushSeconds, "Write snapshot at most once per this many seconds")
	fs.Parse(args)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	fmt.Printf("Starting price stream, writing to %s\n", *snapshotPath)
	if err := pricestream.Run(ctx, *snapshotPath, *flushSeconds); err != nil {
		log.Fatal(err)
	}
}

// ---------- symbols ----------

func runSymbols(args []string) {
	fs := flag.NewFlagSet("symbols", flag.ExitOnError)
	listPath := fs.String("list-path", symbols.DefaultSymbolListPath, "Static symbol list file")
	refresh := fs.Bool("refresh", false, "Force refresh from Binance exchangeInfo")
	stage1Only := fs.Bool("stage1-only", false, "Restrict to BTCUSDT, ETHUSDT only")
	allowlistStr := fs.String("allowlist", "", "Comma-separated symbol allowlist")
	format := fs.String("format", "text", "Output format: text or json")
	fs.Parse(args)

	var allowlist []string
	if *allowlistStr != "" {
		for _, s := range strings.Split(*allowlistStr, ",") {
			s = strings.TrimSpace(s)
			if s != "" {
				allowlist = append(allowlist, s)
			}
		}
	}

	syms, source, err := symbols.GetTargetSymbols(*listPath, *refresh, allowlist, *stage1Only)
	if err != nil {
		log.Fatal(err)
	}

	if *format == "json" {
		result := map[string]interface{}{
			"symbols": syms,
			"source":  source,
			"count":   len(syms),
		}
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		enc.Encode(result)
		return
	}

	fmt.Printf("Source: %s\nSymbols: %d\n\n", source, len(syms))
	for _, s := range syms {
		fmt.Println(s)
	}
}

// findFrontendDir attempts to locate the frontend directory relative to the binary or CWD.
func findFrontendDir() string {
	// Try relative to CWD
	if info, err := os.Stat("frontend"); err == nil && info.IsDir() {
		return "frontend"
	}

	// Try relative to the binary
	execPath, err := os.Executable()
	if err == nil {
		dir := filepath.Dir(execPath)
		candidate := filepath.Join(dir, "..", "frontend")
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			return candidate
		}
	}

	return "frontend"
}
