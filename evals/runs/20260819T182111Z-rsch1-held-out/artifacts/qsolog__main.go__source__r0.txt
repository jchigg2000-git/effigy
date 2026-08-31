// Command qsologd serves the ham-radio-logbook contact API.
//
// Everything it needs is inside this tree: the seed file is ./testdata, the
// database is created under ./data, and the listen address is a literal below
// rather than an allocation looked up in some table living somewhere else.
// Clone the repository, run this, and it works.
//
// Four environment variables override the defaults, each read at its use site:
//
//	QSOLOG_ADDR          listen address              (default :8310)
//	QSOLOG_DB_PATH       SQLite file                 (default ./data/qsolog.db)
//	QSOLOG_SEED_PATH     local log-interchange file  (default ./testdata/log_seed.qlif)
//	QSOLOG_CORS_ORIGINS  comma-separated allow list, read by the API package
//
// The seed is loaded once, on the first boot against an empty database. There
// is no runtime reload route: reseeding means stopping the process, clearing
// the database file, and starting it again.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"qsolog/internal/api"
	"qsolog/internal/ingest"
	"qsolog/internal/store"
)

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func run(logger *slog.Logger) error {
	addr := envOr("QSOLOG_ADDR", ":8310")
	dbPath := envOr("QSOLOG_DB_PATH", "./data/qsolog.db")
	seedPath := envOr("QSOLOG_SEED_PATH", "./testdata/log_seed.qlif")

	if err := os.MkdirAll(filepath.Dir(dbPath), 0o755); err != nil {
		return err
	}
	db, err := store.Open(dbPath)
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
		logger.Info("seeded logbook", "seed", seedPath, "stations", counts.Stations,
			"contacts", counts.Contacts, "confirmations", counts.Confirmations)
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
		logger.Error("qsologd exited", "err", err)
		os.Exit(1)
	}
}
