// Command tailwatchd serves the fleet airworthiness-tracking API.
//
// Everything it needs is inside this tree: the seed file is ./testdata, the
// database is created under ./data, and the listen address is a literal below
// rather than an allocation looked up in some table living somewhere else.
//
// Four environment variables override the defaults, each read at its use site:
//
//	TAILWATCH_ADDR         listen address                (default :8350)
//	TAILWATCH_DB_PATH      SQLite file                    (default ./data/tailwatch.db)
//	TAILWATCH_SEED_PATH    local-profile seed file        (default ./testdata/fleet_seed.twd)
//	TAILWATCH_CORS_ORIGINS comma-separated allow list, read by the API package
//
// The seed is loaded once, on the first boot against an empty database. There
// is no reload route in this service: a re-seed means restarting against a
// fresh database file.
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

	"tailwatch/internal/api"
	"tailwatch/internal/ingest"
)

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func run(logger *slog.Logger) error {
	addr := envOr("TAILWATCH_ADDR", ":8350")
	dbPath := envOr("TAILWATCH_DB_PATH", "./data/tailwatch.db")
	seedPath := envOr("TAILWATCH_SEED_PATH", "./testdata/fleet_seed.twd")

	if err := os.MkdirAll(filepath.Dir(dbPath), 0o755); err != nil {
		return err
	}
	db, err := sql.Open("sqlite", dbPath+"?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)")
	if err != nil {
		return err
	}
	defer db.Close()
	db.SetMaxOpenConns(1)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	loaded, counts, err := ingest.EnsureSeeded(ctx, db, seedPath)
	if err != nil {
		return err
	}
	if loaded {
		logger.Info("seeded fleet", "seed", seedPath, "airframes", counts.Airframes,
			"components", counts.Components, "directives", counts.Directives,
			"applicabilityRules", counts.ApplicabilityRules, "complianceRecords", counts.ComplianceRecords)
	}

	srv := &http.Server{
		Addr:              addr,
		Handler:           api.NewServer(db, logger).Handler(),
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
		logger.Error("tailwatchd exited", "err", err)
		os.Exit(1)
	}
}
