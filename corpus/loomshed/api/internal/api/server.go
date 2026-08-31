package api

import (
	"database/sql"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"strings"

	"github.com/go-chi/chi/v5"

	"loomshed/internal/ingest"
)

// Server carries the dependencies a request handler needs: the database
// handle, the logger, two pieces of runtime configuration, and the router
// they are wired into. Constructed once at startup by NewServer.
type Server struct {
	db         *sql.DB
	logger     *slog.Logger
	seedPath   string
	adminToken string
	router     http.Handler
}

// corsAllowList reads the comma-separated origin list. An empty value means
// the middleware is a no-op, which is the developer-machine default.
func corsAllowList() []string {
	raw := strings.TrimSpace(os.Getenv("LOOMSHED_CORS_ORIGINS"))
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
					w.Header().Set("Access-Control-Allow-Methods", "GET, PATCH, OPTIONS")
					w.Header().Set("Access-Control-Allow-Headers", "Accept, Content-Type, X-Admin-Token")
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
	r.Route("/runs", func(rr chi.Router) {
		rr.Get("/search", s.handleSearchRuns)
		rr.Route("/{runId}", func(ir chi.Router) {
			ir.Get("/", s.handleGetRun)
			ir.Patch("/defects/{defectId}", s.handlePatchDefect)
		})
	})
	r.Route("/looms", func(lr chi.Router) {
		lr.Get("/{loomId}", s.handleGetLoom)
		lr.Get("/{loomId}/utilisation", s.handleLoomUtilisation)
	})
	r.Post("/admin/ingest", s.handleAdminIngest)
	s.router = r
	return s
}

func (s *Server) Handler() http.Handler { return s.router }

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "loomshed"})
}

func (s *Server) serverError(w http.ResponseWriter, err error) {
	s.logger.Error("request failed", "err", err)
	writeError(w, http.StatusInternalServerError, "internal", "internal server error")
}

type apiError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type errorEnvelope struct {
	Error apiError `json:"error"`
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorEnvelope{Error: apiError{Code: code, Message: message}})
}

// ingestResponse reports what an admin-triggered reload found. It is the
// only route in the service that checks anything beyond the request shape.
type ingestResponse struct {
	Reloaded bool          `json:"reloaded"`
	Seed     string        `json:"seed"`
	Counts   ingest.Counts `json:"counts"`
}

func (s *Server) handleAdminIngest(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("X-Admin-Token") != s.adminToken {
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing or invalid admin token")
		return
	}
	counts, err := ingest.FromFile(r.Context(), s.db, s.seedPath)
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, ingestResponse{Reloaded: true, Seed: s.seedPath, Counts: counts})
}
