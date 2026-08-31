// Command meterworksd serves the Cedar Hollow Municipal Water metering API.
//
// Everything it needs is inside this tree: the seed file is ./testdata, the
// database is created under ./data, and the listen address is a literal
// below rather than an allocation looked up in some table living somewhere
// else. Clone the repository, run this, and it works.
//
// Three environment variables override the defaults, each read at its use site:
//
//	METERWORKS_ADDR         listen address       (default :8320)
//	METERWORKS_DB_PATH      SQLite file          (default ./data/meterworks.db)
//	METERWORKS_SEED_PATH    MRIF seed file       (default ./testdata/route_seed.mrif)
//
// The seed is loaded once, on the first boot against an empty database.
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

	"meterworks/internal/api"
	"meterworks/internal/ingest"
)

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func run(logger *slog.Logger) error {
	addr := envOr("METERWORKS_ADDR", ":8320")
	dbPath := envOr("METERWORKS_DB_PATH", "./data/meterworks.db")
	seedPath := envOr("METERWORKS_SEED_PATH", "./testdata/route_seed.mrif")

	if err := os.MkdirAll(filepath.Dir(dbPath), 0o755); err != nil {
		return err
	}
	db, err := sql.Open("sqlite", dbPath)
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
		logger.Info("seeded metering database", "seed", seedPath, "servicePoints", counts.ServicePoints,
			"meters", counts.Meters, "reads", counts.Reads, "billingCycles", counts.BillingCycles)
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
		logger.Error("meterworksd exited", "err", err)
		os.Exit(1)
	}
}
