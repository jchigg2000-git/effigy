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
	raw := strings.TrimSpace(os.Getenv("TREMORLINE_CORS_ORIGINS"))
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
					w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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
	r.Get("/readyz", s.handleReady)
	r.Route("/events", func(er chi.Router) {
		er.Get("/search", s.handleSearchEvents)
		er.Post("/associate", s.handleAssociateDetections)
		er.Get("/{eventId}", s.handleGetEvent)
	})
	r.Route("/stations", func(sr chi.Router) {
		sr.Get("/", s.handleListStations)
		sr.Get("/{stationId}", s.handleGetStationInventory)
	})
	s.router = r
	return s
}

func (s *Server) Handler() http.Handler { return s.router }

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "tremorline"})
}

// handleReady answers the readiness probe by counting the station inventory.
// The query runs here, against the struct's own handle, because there is
// nowhere else for it to live: the store package hands out a raw handle and
// nothing more.
func (s *Server) handleReady(w http.ResponseWriter, r *http.Request) {
	var n int
	if err := s.db.QueryRowContext(r.Context(), `SELECT count(*) FROM stations`).Scan(&n); err != nil {
		writeError(w, http.StatusServiceUnavailable, "db_error", err.Error())
		return
	}
	if n == 0 {
		writeError(w, http.StatusServiceUnavailable, "not_seeded", "no stations loaded")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "stations": n})
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
