package api

import (
	"database/sql"
	"errors"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"

	"qsolog/internal/model"
)

// handleGetStation looks up one operator station. The station id is the
// callsign itself — there is no separate surrogate id anywhere in this
// service — so this is a single-column lookup with no join.
//
// A station that has never logged a contact is still a valid row: ingest
// creates one on first sight of a callsign in the op field, profile fields
// or not, so a lookup here can succeed even for an operator with zero
// contacts recorded yet.
func (s *Server) handleGetStation(w http.ResponseWriter, r *http.Request) {
	stationID := strings.TrimSpace(chi.URLParam(r, "stationId"))
	var st model.Station
	err := s.db.QueryRowContext(r.Context(), `SELECT station_id, callsign,
	              COALESCE(grid_square,''), COALESCE(operator_class,'')
	       FROM stations WHERE station_id = ?`, stationID).
		Scan(&st.StationID, &st.Callsign, &st.GridSquare, &st.OperatorClass)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "station not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, st)
}

// handleStationSummary answers "how much has this station logged" without the
// band/mode breakdown handleAwardProgress gives: one row, four counts, no
// grouping. It exists because the SPA's station header needs a cheap number on
// every page load, not the full progress table.
func (s *Server) handleStationSummary(w http.ResponseWriter, r *http.Request) {
	stationID := strings.TrimSpace(chi.URLParam(r, "stationId"))
	var known string
	err := s.db.QueryRowContext(r.Context(),
		`SELECT station_id FROM stations WHERE station_id = ?`, stationID).Scan(&known)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "station not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}

	var totalContacts, distinctBands, distinctModes, confirmedContacts int
	err = s.db.QueryRowContext(r.Context(), `SELECT count(*), count(DISTINCT band),
	              count(DISTINCT mode), count(*) FILTER (WHERE confirmed_on IS NOT NULL)
	       FROM contacts WHERE station_id = ?`, stationID).
		Scan(&totalContacts, &distinctBands, &distinctModes, &confirmedContacts)
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"stationId":         stationID,
		"totalContacts":     totalContacts,
		"distinctBands":     distinctBands,
		"distinctModes":     distinctModes,
		"confirmedContacts": confirmedContacts,
	})
}
