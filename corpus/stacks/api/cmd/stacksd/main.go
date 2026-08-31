// Command stacksd serves the inter-branch catalog and circulation API.
//
// Everything it needs is inside this tree: the seed file is ./testdata, the
// database is created under ./data, and the listen address is a literal below
// rather than an allocation looked up in some table living somewhere else. Clone
// the repository, run this, and it works.
//
// Five environment variables override the defaults, each read at its use site:
//
//	STACKS_ADDR         listen address        (default :8300)
//	STACKS_DB_PATH      SQLite file           (default ./data/stacks.db)
//	STACKS_SEED_PATH    MARCMaker seed file   (default ./testdata/catalog_seed.mrk)
//	STACKS_ADMIN_TOKEN  token for /admin/ingest
//	STACKS_CORS_ORIGINS comma-separated allow list, read by the API package
//
// The seed is loaded once, on the first boot against an empty database. Reloading
// it afterwards is a POST to /admin/ingest with the admin token, which is the only
// route in the service that checks anything at all.
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

	"stacks/internal/api"
	"stacks/internal/ingest"
	"stacks/internal/store"
)

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func run(logger *slog.Logger) error {
	addr := envOr("STACKS_ADDR", ":8300")
	dbPath := envOr("STACKS_DB_PATH", "./data/stacks.db")
	seedPath := envOr("STACKS_SEED_PATH", "./testdata/catalog_seed.mrk")
	// dev-only, not a secret
	adminToken := envOr("STACKS_ADMIN_TOKEN", "localdev")

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
		logger.Info("seeded catalog", "seed", seedPath, "holdings", counts.Holdings,
			"branches", counts.Branches, "loans", counts.Loans,
			"borrowers", counts.Borrowers, "reservations", counts.Reservations)
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
		logger.Error("stacksd exited", "err", err)
		os.Exit(1)
	}
}
