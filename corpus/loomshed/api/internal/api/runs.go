// Package api implements the loomshed HTTP surface: run detail assembled
// from per-shift output rows, run search, and a defect-entry PATCH handler
// here, plus the smaller loom resource in looms.go.
package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"loomshed/internal/model"
)

// loadRun pulls a production run and the loom, yarn lot, and order it
// references in one four-way join. Shift output and defect rows are not
// part of this query — they are loaded separately by the caller and folded
// in, because a run can carry a variable number of each and a single flat
// SELECT would duplicate the parent row once per child.
func (s *Server) loadRun(ctx context.Context, runID string) (model.Run, error) {
	var run model.Run
	var loom model.LoomRef
	var lot model.LotRef
	var ord model.OrderRef
	err := s.db.QueryRowContext(ctx, `SELECT r.run_id, r.loom_id, r.lot_id, r.order_id,
	              r.started_on, r.status,
	              l.loom_id, COALESCE(l.name,''), COALESCE(l.loom_type,''),
	              y.lot_id, COALESCE(y.fiber_blend,''), COALESCE(y.denier_count,0),
	              o.order_id, COALESCE(o.fabric_spec,''), COALESCE(o.customer_id,'')
	       FROM runs r
	       JOIN looms l ON l.loom_id = r.loom_id
	       JOIN yarn_lots y ON y.lot_id = r.lot_id
	       JOIN orders o ON o.order_id = r.order_id
	       WHERE r.run_id = ?`, runID).
		Scan(&run.RunID, &run.LoomID, &run.LotID, &run.OrderID, &run.StartedOn, &run.Status,
			&loom.LoomID, &loom.Name, &loom.LoomType,
			&lot.LotID, &lot.FiberBlend, &lot.DenierCount,
			&ord.OrderID, &ord.FabricSpec, &ord.CustomerID)
	if err != nil {
		return model.Run{}, err
	}
	run.Loom = &loom
	run.Lot = &lot
	run.Order = &ord
	return run, nil
}

// loadShiftOutputs reads every shift logged against a run, oldest first.
// This is the source of truth for a run's totals: nothing on the runs row
// itself carries output or downtime.
func (s *Server) loadShiftOutputs(ctx context.Context, runID string) ([]model.ShiftOutput, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT shift_date, shift_code, COALESCE(operator_id,''),
	              output_m, COALESCE(picks_per_minute,0), downtime_min
	       FROM shift_outputs WHERE run_id = ?
	       ORDER BY shift_date, shift_code`, runID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.ShiftOutput{}
	for rows.Next() {
		var so model.ShiftOutput
		if err := rows.Scan(&so.ShiftDate, &so.ShiftCode, &so.OperatorID,
			&so.OutputM, &so.PicksPerMinute, &so.DowntimeMin); err != nil {
			return nil, err
		}
		out = append(out, so)
	}
	return out, rows.Err()
}

// loadDefects reads every defect logged against a run, oldest first.
func (s *Server) loadDefects(ctx context.Context, runID string) ([]model.Defect, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT id, shift_date, shift_code, defect_type,
	              severity, meters_at, COALESCE(note,''), status
	       FROM defects WHERE run_id = ?
	       ORDER BY shift_date, id`, runID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.Defect{}
	for rows.Next() {
		var d model.Defect
		if err := rows.Scan(&d.DefectID, &d.ShiftDate, &d.ShiftCode, &d.DefectType,
			&d.Severity, &d.MetersAt, &d.Note, &d.Status); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

// assembleRun loads the shift and defect children and folds them into the
// run, computing the two totals the detail view leads with. Search results
// never call this — only the single-run read path pays for the two extra
// queries and the summation.
func (s *Server) assembleRun(ctx context.Context, runID string) (model.Run, error) {
	run, err := s.loadRun(ctx, runID)
	if err != nil {
		return model.Run{}, err
	}
	shifts, err := s.loadShiftOutputs(ctx, runID)
	if err != nil {
		return model.Run{}, err
	}
	defects, err := s.loadDefects(ctx, runID)
	if err != nil {
		return model.Run{}, err
	}
	for _, so := range shifts {
		run.OutputTotalM += so.OutputM
		run.DowntimeTotalMin += so.DowntimeMin
	}
	run.Shifts = shifts
	run.Defects = defects
	return run, nil
}

func (s *Server) handleGetRun(w http.ResponseWriter, r *http.Request) {
	runID := strings.TrimSpace(chi.URLParam(r, "runId"))
	run, err := s.assembleRun(r.Context(), runID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "run not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, run)
}

type runSummary struct {
	RunID     string `json:"runId"`
	LoomID    string `json:"loomId"`
	LotID     string `json:"lotId"`
	OrderID   string `json:"orderId"`
	StartedOn string `json:"startedOn"`
	Status    string `json:"status"`
}

// handleSearchRuns filters on exact matches and a started-on date window
// rather than substring text: run, loom, lot and order ids are opaque
// codes, not titles, so LIKE has nothing to offer here that "=" doesn't
// already do.
func (s *Server) handleSearchRuns(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	conds := []string{}
	args := []any{}
	if v := strings.TrimSpace(q.Get("loomId")); v != "" {
		conds = append(conds, "loom_id = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("lotId")); v != "" {
		conds = append(conds, "lot_id = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("orderId")); v != "" {
		conds = append(conds, "order_id = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("status")); v != "" {
		conds = append(conds, "status = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("from")); v != "" {
		conds = append(conds, "started_on >= ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("to")); v != "" {
		conds = append(conds, "started_on <= ?")
		args = append(args, v)
	}
	if len(conds) == 0 {
		writeError(w, http.StatusBadRequest, "bad_request",
			"at least one filter required (loomId, lotId, orderId, status, from, to)")
		return
	}
	limit := 50
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("limit"))); err == nil && n > 0 && n <= 200 {
		limit = n
	}
	sqlStr := `SELECT run_id, loom_id, lot_id, order_id, started_on, status
	           FROM runs WHERE ` + strings.Join(conds, " AND ") +
		" ORDER BY started_on DESC, run_id LIMIT ?"
	args = append(args, limit)
	rows, err := s.db.QueryContext(r.Context(), sqlStr, args...)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []runSummary{}
	for rows.Next() {
		var rs runSummary
		if err := rows.Scan(&rs.RunID, &rs.LoomID, &rs.LotID, &rs.OrderID,
			&rs.StartedOn, &rs.Status); err != nil {
			s.serverError(w, err)
			return
		}
		out = append(out, rs)
	}
	if err := rows.Err(); err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"count": len(out),
		"limit": limit,
		"runs":  out,
	})
}

// defectPatch carries pointers so "absent from the body" stays
// distinguishable from "present and set to zero/empty". defectType and
// shift are not represented here and cannot be written over HTTP: a
// defect's type and the shift it was found on are ingest-derived facts, not
// review-time edits. Typical values ingest has produced for defectType:
// WARP-BREAK, WEFT-SNAG, SHUTTLE-JAM, REED-MARK, SELVEDGE-FRAY,
// HEDDLE-STICK, TENSION-DRIFT — the token vocabulary is set by the shift
// report's own DEFECT line, not by an enum on this side.
type defectPatch struct {
	Status   *string  `json:"status"`
	Severity *int     `json:"severity"`
	Note     *string  `json:"note"`
	MetersAt *float64 `json:"metersAt"`
}

// statusRank fixes the one-way review lifecycle: a defect can move forward
// from open to reviewed to resolved but a PATCH can never send it backwards.
var statusRank = map[string]int{"open": 0, "reviewed": 1, "resolved": 2}

// validateAndBuild returns the SET fragments, their bind arguments, and a
// bad-request message when a value fails a rule. currentStatus and
// outputTotal are looked up by the caller before validation runs, because
// the status transition and the metersAt bound both need state this struct
// does not carry on its own.
func (p *defectPatch) validateAndBuild(currentStatus string, outputTotal float64) ([]string, []any, string) {
	setParts := []string{}
	args := []any{}
	set := func(col string, val any) {
		setParts = append(setParts, col+" = ?")
		args = append(args, val)
	}
	if p.Status != nil {
		v := strings.ToLower(strings.TrimSpace(*p.Status))
		newRank, ok := statusRank[v]
		if !ok {
			return nil, nil, "status must be one of open, reviewed, resolved"
		}
		if newRank < statusRank[currentStatus] {
			return nil, nil, "status cannot move backwards from " + currentStatus
		}
		set("status", v)
	}
	if p.Severity != nil {
		if *p.Severity < 1 || *p.Severity > 3 {
			return nil, nil, "severity must be between 1 and 3"
		}
		set("severity", *p.Severity)
	}
	if p.Note != nil {
		v := strings.TrimSpace(*p.Note)
		if len(v) > 240 {
			return nil, nil, "note must be 240 characters or fewer"
		}
		set("note", v)
	}
	if p.MetersAt != nil {
		if *p.MetersAt < 0 {
			return nil, nil, "metersAt must not be negative"
		}
		if *p.MetersAt > outputTotal {
			return nil, nil, "metersAt cannot exceed the run's woven output total"
		}
		set("meters_at", *p.MetersAt)
	}
	return setParts, args, ""
}

// handlePatchDefect reviews one defect against the run's own state: the
// current status gates the transition and the current output total gates
// metersAt, so both are read before the patch is validated rather than
// trusted from the request body.
func (s *Server) handlePatchDefect(w http.ResponseWriter, r *http.Request) {
	runID := strings.TrimSpace(chi.URLParam(r, "runId"))
	defectID := strings.TrimSpace(chi.URLParam(r, "defectId"))
	if ct := r.Header.Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		writeError(w, http.StatusBadRequest, "bad_request", "Content-Type must be application/json")
		return
	}
	var p defectPatch
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err.Error())
		return
	}
	var currentStatus string
	err := s.db.QueryRowContext(r.Context(),
		`SELECT status FROM defects WHERE id = ? AND run_id = ?`, defectID, runID).Scan(&currentStatus)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "defect not found on this run")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	var outputTotal float64
	if err := s.db.QueryRowContext(r.Context(),
		`SELECT COALESCE(SUM(output_m),0) FROM shift_outputs WHERE run_id = ?`, runID).Scan(&outputTotal); err != nil {
		s.serverError(w, err)
		return
	}
	setParts, setArgs, badReq := p.validateAndBuild(currentStatus, outputTotal)
	if badReq != "" {
		writeError(w, http.StatusBadRequest, "bad_request", badReq)
		return
	}
	if len(setParts) == 0 {
		writeError(w, http.StatusBadRequest, "bad_request", "request body had no updatable fields")
		return
	}
	setArgs = append(setArgs, defectID, runID)
	upd := fmt.Sprintf(`UPDATE defects SET %s WHERE id = ? AND run_id = ?`, strings.Join(setParts, ", "))
	if _, err := s.db.ExecContext(r.Context(), upd, setArgs...); err != nil {
		s.serverError(w, err)
		return
	}
	run, err := s.assembleRun(r.Context(), runID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, run)
}
