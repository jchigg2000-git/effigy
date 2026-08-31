// Command loomshedd serves the Ashcombe Weaving Works production-tracking
// API. Everything it needs is inside this tree: the seed file is
// ./testdata, the database is created under ./data, and the listen address
// is a literal below. Clone the repository, run this, and it works.
//
// Five environment variables override the defaults, each read at its use site:
//
//	LOOMSHED_ADDR         listen address          (default :8340)
//	LOOMSHED_DB_PATH      SQLite file             (default ./data/loomshed.db)
//	LOOMSHED_SEED_PATH    shift-report seed file  (default ./testdata/shift_seed.txt)
//	LOOMSHED_ADMIN_TOKEN  token for /admin/ingest
//	LOOMSHED_CORS_ORIGINS comma-separated allow list, read by the API package
//
// The seed loads once on first boot against an empty database. Reloading it
// afterwards is a POST to /admin/ingest with the admin token.
package main

import (
	"context"
	"database/sql"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	_ "modernc.org/sqlite"

	"loomshed/internal/api"
	"loomshed/internal/ingest"
)

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

// openDB opens the SQLite file and creates the schema if it is not already
// there. There is no separate migration tool: six CREATE TABLE statements,
// run every boot, is the whole of it.
func openDB(path string) (*sql.DB, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS looms (loom_id TEXT PRIMARY KEY, name TEXT, loom_type TEXT, width_cm INTEGER)`,
		`CREATE TABLE IF NOT EXISTS yarn_lots (lot_id TEXT PRIMARY KEY, fiber_blend TEXT, denier_count INTEGER, supplier_code TEXT, received_on TEXT)`,
		`CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT, fabric_spec TEXT, quantity_m REAL, due_on TEXT)`,
		`CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, loom_id TEXT, lot_id TEXT, order_id TEXT, started_on TEXT, status TEXT)`,
		`CREATE TABLE IF NOT EXISTS shift_outputs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, shift_date TEXT, shift_code TEXT, operator_id TEXT, output_m REAL, picks_per_minute INTEGER, downtime_min INTEGER)`,
		`CREATE TABLE IF NOT EXISTS defects (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, shift_date TEXT, shift_code TEXT, defect_type TEXT, severity INTEGER, meters_at REAL, note TEXT, status TEXT)`,
	}
	for _, stmt := range stmts {
		if _, err := db.Exec(stmt); err != nil {
			db.Close()
			return nil, err
		}
	}
	return db, nil
}

func run(logger *slog.Logger) error {
	addr := envOr("LOOMSHED_ADDR", ":8340")
	dbPath := envOr("LOOMSHED_DB_PATH", "./data/loomshed.db")
	seedPath := envOr("LOOMSHED_SEED_PATH", "./testdata/shift_seed.txt")
	// dev-only, not a secret
	adminToken := envOr("LOOMSHED_ADMIN_TOKEN", "dev")
	if err := os.MkdirAll(filepath.Dir(dbPath), 0o755); err != nil {
		return err
	}
	db, err := openDB(dbPath)
	if err != nil {
		return err
	}
	defer db.Close()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	loaded, counts, err := ingest.EnsureSeeded(ctx, db, seedPath)
	if err != nil {
		return err
	}
	if loaded {
		logger.Info("seeded production database", "seed", seedPath,
			"looms", counts.Looms, "runs", counts.Runs, "shiftOutputs", counts.ShiftOutputs)
	}
	srv := &http.Server{
		Addr:              addr,
		Handler:           api.NewServer(db, logger, seedPath, adminToken).Handler(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdownCtx)
	}()
	logger.Info("listening", "addr", addr, "db", dbPath, "seed", seedPath)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	logger.Info("stopped")
	return nil
}

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	if err := run(logger); err != nil {
		logger.Error("loomshedd exited", "err", err)
		os.Exit(1)
	}
}
