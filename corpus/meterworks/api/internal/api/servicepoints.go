package api

import (
	"database/sql"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"meterworks/internal/model"
)

func (s *Server) handleGetServicePoint(w http.ResponseWriter, r *http.Request) {
	spID := strings.TrimSpace(chi.URLParam(r, "spId"))
	var sp model.ServicePoint
	var mt model.Meter
	err := s.db.QueryRowContext(r.Context(), `SELECT sp.service_point_id, sp.route_code,
	              COALESCE(sp.account_ref,''), m.meter_id, m.serial_number,
	              COALESCE(m.size_code,'')
	       FROM service_points sp
	       JOIN meters m ON m.service_point_id = sp.service_point_id
	       WHERE sp.service_point_id = ?`, spID).Scan(&sp.ServicePointID, &sp.RouteCode,
		&sp.AccountRef, &mt.MeterID, &mt.SerialNumber, &mt.SizeCode)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "service point not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	sp.Meter = &mt
	writeJSON(w, http.StatusOK, sp)
}

// handleServicePointReads returns the read history at one service point,
// most recent first. Unlike the route listing, a service point that does
// not exist is a 404: it is a first-class row, not an inferred grouping.
func (s *Server) handleServicePointReads(w http.ResponseWriter, r *http.Request) {
	spID := strings.TrimSpace(chi.URLParam(r, "spId"))
	q := r.URL.Query()
	limit := 50
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("limit"))); err == nil && n > 0 && n <= 500 {
		limit = n
	}
	offset := 0
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("offset"))); err == nil && n > 0 {
		offset = n
	}

	var known string
	err := s.db.QueryRowContext(r.Context(),
		`SELECT service_point_id FROM service_points WHERE service_point_id = ?`, spID).Scan(&known)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "service point not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}

	rows, err := s.db.QueryContext(r.Context(), `SELECT read_id, meter_id, read_type,
	              read_value, read_date, tolerance_flag
	       FROM reads WHERE service_point_id = ?
	       ORDER BY read_date DESC LIMIT ? OFFSET ?`, spID, limit, offset)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []readSummary{}
	for rows.Next() {
		var it readSummary
		it.ServicePointID = spID
		if err := rows.Scan(&it.ReadID, &it.MeterID, &it.ReadType, &it.ReadValue,
			&it.ReadDate, &it.ToleranceFlag); err != nil {
			s.serverError(w, err)
			return
		}
		out = append(out, it)
	}
	if err := rows.Err(); err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"servicePointId": spID,
		"count":          len(out),
		"limit":          limit,
		"offset":         offset,
		"reads":          out,
	})
}
