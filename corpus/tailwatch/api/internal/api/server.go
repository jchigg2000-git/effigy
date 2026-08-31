package api

import (
	"database/sql"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"strings"

	"github.com/go-chi/chi/v5"
)

// Server carries the dependencies a request handler needs: the database handle,
// the logger, and the router they are wired into. Constructed once at startup
// by NewServer.
type Server struct {
	db     *sql.DB
	logger *slog.Logger
	router http.Handler
}

// corsAllowList reads the comma-separated origin list. An empty value means the
// middleware is a no-op, which is the developer-machine default.
func corsAllowList() []string {
	raw := strings.TrimSpace(os.Getenv("TAILWATCH_CORS_ORIGINS"))
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
					w.Header().Set("Access-Control-Allow-Headers", "Accept, Content-Type")
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

func NewServer(db *sql.DB, logger *slog.Logger) *Server {
	s := &Server{db: db, logger: logger}
	r := chi.NewRouter()
	r.Use(corsMiddleware)
	r.Get("/healthz", s.handleHealth)
	r.Get("/readyz", s.handleReady)
	r.Route("/components", func(cr chi.Router) {
		cr.Get("/search", s.handleSearchComponents)
		cr.Route("/{componentId}", func(ir chi.Router) {
			ir.Get("/", s.handleGetComponent)
			ir.Patch("/", s.handlePatchComponent)
			ir.Get("/compliance", s.handleGetComponentCompliance)
		})
	})
	r.Route("/directives", func(dr chi.Router) {
		dr.Get("/{directiveId}", s.handleGetDirective)
		dr.Get("/{directiveId}/compliance", s.handleDirectiveCompliance)
	})
	s.router = r
	return s
}

func (s *Server) Handler() http.Handler { return s.router }

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "tailwatch"})
}

// handleReady answers the readiness probe by counting tracked components. The
// query runs here, against the struct's own handle, because there is nowhere
// else for it to live: nothing hands out a narrower query surface.
func (s *Server) handleReady(w http.ResponseWriter, r *http.Request) {
	var n int
	if err := s.db.QueryRowContext(r.Context(), `SELECT count(*) FROM components`).Scan(&n); err != nil {
		writeError(w, http.StatusServiceUnavailable, "db_error", err.Error())
		return
	}
	if n == 0 {
		writeError(w, http.StatusServiceUnavailable, "not_seeded", "no components loaded")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "components": n})
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
