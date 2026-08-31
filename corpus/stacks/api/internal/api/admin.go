package api

import (
	"net/http"

	"stacks/internal/ingest"
)

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
