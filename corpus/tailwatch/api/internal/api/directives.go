package api

import (
	"database/sql"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"tailwatch/internal/model"
)

func (s *Server) handleGetDirective(w http.ResponseWriter, r *http.Request) {
	directiveID := strings.TrimSpace(chi.URLParam(r, "directiveId"))
	var d model.Directive
	err := s.db.QueryRowContext(r.Context(),
		`SELECT directive_id, title, issued_by, category
	       FROM directives WHERE directive_id = ?`, directiveID).
		Scan(&d.DirectiveID, &d.Title, &d.IssuedBy, &d.Category)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "directive not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, d)
}

// handleDirectiveCompliance pages every compliance check recorded against one
// directive, across every airframe in the fleet it has ever been checked
// against. This is the fleet-wide view; loadCompliance in components.go is the
// mirror image, one component's history across every directive it has been
// checked against.
func (s *Server) handleDirectiveCompliance(w http.ResponseWriter, r *http.Request) {
	directiveID := strings.TrimSpace(chi.URLParam(r, "directiveId"))
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
		`SELECT directive_id FROM directives WHERE directive_id = ?`, directiveID).Scan(&known)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "directive not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}

	rows, err := s.db.QueryContext(r.Context(), `SELECT r.component_id, c.tail_number,
	              r.complied_on, r.method, COALESCE(r.next_due_on,''), r.status
	       FROM compliance_records r
	       JOIN components c ON c.component_id = r.component_id
	       WHERE r.directive_id = ?
	       ORDER BY r.complied_on DESC, r.component_id LIMIT ? OFFSET ?`,
		directiveID, limit, offset)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()

	type complianceRow struct {
		ComponentID string `json:"componentId"`
		TailNumber  string `json:"tailNumber"`
		CompliedOn  string `json:"compliedOn"`
		Method      string `json:"method"`
		NextDueOn   string `json:"nextDueOn,omitempty"`
		Status      string `json:"status"`
	}
	out := []complianceRow{}
	for rows.Next() {
		var it complianceRow
		if err := rows.Scan(&it.ComponentID, &it.TailNumber, &it.CompliedOn, &it.Method,
			&it.NextDueOn, &it.Status); err != nil {
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
		"directiveId": directiveID,
		"count":       len(out),
		"limit":       limit,
		"offset":      offset,
		"compliance":  out,
	})
}
