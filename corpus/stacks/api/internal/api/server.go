package api

import (
	"database/sql"
	"log/slog"
	"net/http"
	"os"
	"strings"

	"github.com/go-chi/chi/v5"
)

// Server carries the dependencies a request handler needs: the database handle,
// the logger, two pieces of runtime configuration, and the router they are wired
// into. Constructed once at startup by NewServer.
type Server struct {
	db         *sql.DB
	logger     *slog.Logger
	seedPath   string
	adminToken string
	router     http.Handler
}

// corsAllowList reads the comma-separated origin list. An empty value means the
// middleware is a no-op, which is the developer-machine default.
func corsAllowList() []string {
	raw := strings.TrimSpace(os.Getenv("STACKS_CORS_ORIGINS"))
	if raw == "" {
		return nil
	}
	out := []string{}
	for _, part := range strings.Split(raw, ",") {
		if p := strings.TrimSpace(part); p != "" {
			out = append(out, p)
		}
	}
	return out
}

func corsMiddleware(next http.Handler) http.Handler {
	allow := corsAllowList()
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin != "" && len(allow) > 0 {
			for _, a := range allow {
				if a == origin || a == "*" {
					w.Header().Set("Access-Control-Allow-Origin", origin)
					w.Header().Set("Vary", "Origin")
					w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
					w.Header().Set("Access-Control-Allow-Headers", "Accept, Content-Type, X-Admin-Token")
					w.Header().Set("Access-Control-Expose-Headers", "X-Request-Id")
					w.Header().Set("Access-Control-Max-Age", "300")
					break
				}
			}
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func NewServer(db *sql.DB, logger *slog.Logger, seedPath, adminToken string) *Server {
	s := &Server{db: db, logger: logger, seedPath: seedPath, adminToken: adminToken}
	r := chi.NewRouter()
	r.Use(corsMiddleware)
	r.Get("/healthz", s.handleHealth)
	r.Get("/readyz", s.handleReady)
	r.Route("/holdings", func(hr chi.Router) {
		hr.Get("/search", s.handleSearchHoldings)
		hr.Route("/{holdingId}", func(ir chi.Router) {
			ir.Get("/", s.handleGetHolding)
			ir.Patch("/", s.handlePatchHolding)
			ir.Get("/loans", s.handleGetLoans)
			ir.Get("/export/dc", s.handleExportDC)
		})
	})
	r.Route("/branches", func(br chi.Router) {
		br.Get("/{branchId}", s.handleGetBranch)
		br.Get("/{branchId}/holdings", s.handleBranchShelflist)
	})
	r.Post("/admin/ingest", s.handleAdminIngest)
	s.router = r
	return s
}

func (s *Server) Handler() http.Handler { return s.router }

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "stacks"})
}

// handleReady answers the readiness probe by counting shelved items. The query
// runs here, against the struct's own handle, because there is nowhere else for
// it to live: the store package hands out a raw handle and nothing more.
func (s *Server) handleReady(w http.ResponseWriter, r *http.Request) {
	var n int
	if err := s.db.QueryRowContext(r.Context(), `SELECT count(*) FROM holdings`).Scan(&n); err != nil {
		writeError(w, http.StatusServiceUnavailable, "db_error", err.Error())
		return
	}
	if n == 0 {
		writeError(w, http.StatusServiceUnavailable, "not_seeded", "no holdings loaded")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "holdings": n})
}

func (s *Server) serverError(w http.ResponseWriter, err error) {
	s.logger.Error("request failed", "err", err)
	writeError(w, http.StatusInternalServerError, "internal", "internal server error")
}
