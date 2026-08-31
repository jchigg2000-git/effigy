package api

import (
	"database/sql"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"stacks/internal/model"
)

func (s *Server) handleGetBranch(w http.ResponseWriter, r *http.Request) {
	branchID := strings.TrimSpace(chi.URLParam(r, "branchId"))
	var b model.Branch
	err := s.db.QueryRowContext(r.Context(), `SELECT branch_id, name,
	              COALESCE(registry_symbol,''), COALESCE(system_id,'')
	       FROM branches WHERE branch_id = ?`, branchID).
		Scan(&b.BranchID, &b.Name, &b.RegistrySymbol, &b.SystemID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "branch not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, b)
}

// handleBranchShelflist pages the items a branch shelves. Reservations are never
// joined in here even though the queue is keyed by the same holding id.
func (s *Server) handleBranchShelflist(w http.ResponseWriter, r *http.Request) {
	branchID := strings.TrimSpace(chi.URLParam(r, "branchId"))
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
		`SELECT branch_id FROM branches WHERE branch_id = ?`, branchID).Scan(&known)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "branch not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}

	rows, err := s.db.QueryContext(r.Context(), `SELECT holding_id, branch_id, author, title,
	              published, COALESCE(room,''), COALESCE(wing,''), COALESCE(bin,'')
	       FROM holdings WHERE branch_id = ?
	       ORDER BY call_number, title LIMIT ? OFFSET ?`, branchID, limit, offset)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()

	out := []holdingSummary{}
	for rows.Next() {
		var it holdingSummary
		if err := rows.Scan(&it.HoldingID, &it.BranchID, &it.Author, &it.Title,
			&it.Published, &it.Room, &it.Wing, &it.Bin); err != nil {
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
		"branchId": branchID,
		"count":    len(out),
		"limit":    limit,
		"offset":   offset,
		"holdings": out,
	})
}
