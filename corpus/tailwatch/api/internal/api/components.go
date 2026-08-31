package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"

	"tailwatch/internal/model"
)

// lifeInput is how far a component has travelled since the clock it is being
// measured against was last zeroed: wear accrued in flight hours, flight
// cycles, and calendar days.
type lifeInput struct {
	HoursSince  float64
	CyclesSince int
	DaysSince   int
}

// lifeLimit is the ceiling on each of those three units. Any of the three may
// be unset for a given part: some parts are cycle-limited only, others are
// calendar-limited only.
type lifeLimit struct {
	Hours  sql.NullFloat64
	Cycles sql.NullInt64
	Days   sql.NullInt64
}

// computeRemaining applies the whichever-comes-first rule across the three
// parallel tracking units. Raw hours, cycles and days are not comparable
// numbers, so "first" is decided by fraction of each unit's own limit already
// consumed; the unit with the highest fraction is the one that will hit zero
// soonest and becomes GoverningUnit. A part with no limit set on a unit simply
// omits that unit from both the comparison and the response.
func computeRemaining(in lifeInput, lim lifeLimit) model.RemainingLife {
	var out model.RemainingLife
	best := -1.0
	if lim.Hours.Valid && lim.Hours.Float64 > 0 {
		remaining := lim.Hours.Float64 - in.HoursSince
		out.RemainingHours = &remaining
		if frac := in.HoursSince / lim.Hours.Float64; frac > best {
			best = frac
			out.GoverningUnit = "HOURS"
		}
	}
	if lim.Cycles.Valid && lim.Cycles.Int64 > 0 {
		remaining := int(lim.Cycles.Int64) - in.CyclesSince
		out.RemainingCycles = &remaining
		if frac := float64(in.CyclesSince) / float64(lim.Cycles.Int64); frac > best {
			best = frac
			out.GoverningUnit = "CYCLES"
		}
	}
	if lim.Days.Valid && lim.Days.Int64 > 0 {
		remaining := int(lim.Days.Int64) - in.DaysSince
		out.RemainingDays = &remaining
		if frac := float64(in.DaysSince) / float64(lim.Days.Int64); frac > best {
			best = frac
			out.GoverningUnit = "CALENDAR_DAYS"
		}
	}
	return out
}

// loadComponent pulls a tracked component, the airframe it is installed on,
// and the life limit its part number carries, then derives remaining life
// from the difference between the airframe's current totals and the totals
// recorded at install time. The life limit join is a LEFT JOIN because most
// part numbers never appear in life_limits at all: no limit, no ceiling.
func (s *Server) loadComponent(ctx context.Context, componentID string) (model.Component, error) {
	var c model.Component
	var af model.Airframe
	var lim lifeLimit
	var installedHours float64
	var installedCycles int
	err := s.db.QueryRowContext(ctx, `SELECT c.component_id, c.tail_number, c.position_code,
	              COALESCE(c.parent_position_code,''), c.category, c.label, c.part_number,
	              c.serial_number, c.installed_on, c.installed_hours, c.installed_cycles,
	              a.tail_number, a.type_designation, a.operator_code, a.total_hours,
	              a.total_cycles, a.status, l.limit_hours, l.limit_cycles, l.limit_calendar_days
	       FROM components c
	       JOIN airframes a ON a.tail_number = c.tail_number
	       LEFT JOIN life_limits l ON l.part_number = c.part_number
	       WHERE c.component_id = ?`, componentID).
		Scan(&c.ComponentID, &c.TailNumber, &c.PositionCode, &c.ParentPositionCode, &c.Category,
			&c.Label, &c.PartNumber, &c.SerialNumber, &c.InstalledOn, &installedHours, &installedCycles,
			&af.TailNumber, &af.TypeDesignation, &af.OperatorCode, &af.TotalHours, &af.TotalCycles,
			&af.Status, &lim.Hours, &lim.Cycles, &lim.Days)
	if err != nil {
		return model.Component{}, err
	}
	c.Airframe = &af
	daysSince := 0
	if installedOn, perr := time.Parse("2006-01-02", c.InstalledOn); perr == nil {
		daysSince = int(time.Since(installedOn).Hours() / 24)
	}
	remaining := computeRemaining(lifeInput{
		HoursSince:  af.TotalHours - installedHours,
		CyclesSince: af.TotalCycles - installedCycles,
		DaysSince:   daysSince,
	}, lim)
	c.Remaining = &remaining
	return c, nil
}

// loadCompliance reads every directive check ever recorded against one
// component, newest first, with the directive's own title and issuer carried
// along so the list renders without a second lookup per row.
func (s *Server) loadCompliance(ctx context.Context, componentID string) ([]model.ComplianceRecord, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT d.directive_id, d.title, d.issued_by, d.category,
	              r.complied_on, r.method, COALESCE(r.next_due_on,''), r.status
	       FROM compliance_records r
	       JOIN directives d ON d.directive_id = r.directive_id
	       WHERE r.component_id = ?
	       ORDER BY r.complied_on DESC`, componentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.ComplianceRecord{}
	for rows.Next() {
		var cr model.ComplianceRecord
		if err := rows.Scan(&cr.Directive.DirectiveID, &cr.Directive.Title, &cr.Directive.IssuedBy,
			&cr.Directive.Category, &cr.CompliedOn, &cr.Method, &cr.NextDueOn, &cr.Status); err != nil {
			return nil, err
		}
		out = append(out, cr)
	}
	return out, rows.Err()
}

func (s *Server) handleGetComponent(w http.ResponseWriter, r *http.Request) {
	componentID := strings.TrimSpace(chi.URLParam(r, "componentId"))
	c, err := s.loadComponent(r.Context(), componentID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "component not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	compliance, err := s.loadCompliance(r.Context(), componentID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	c.Compliance = compliance
	writeJSON(w, http.StatusOK, c)
}

func (s *Server) handleGetComponentCompliance(w http.ResponseWriter, r *http.Request) {
	componentID := strings.TrimSpace(chi.URLParam(r, "componentId"))
	var probe string
	err := s.db.QueryRowContext(r.Context(),
		`SELECT component_id FROM components WHERE component_id = ?`, componentID).Scan(&probe)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "component not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	compliance, err := s.loadCompliance(r.Context(), componentID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"componentId": componentID,
		"count":       len(compliance),
		"compliance":  compliance,
	})
}

// handleSearchComponents is the drill-down entry point. positionCode is a
// dot-separated path ("ENG-1", "ENG-1.FAN", "ENG-1.FAN.BLADE-01"), so sorting
// on it lexicographically walks the hierarchy: a parent position always sorts
// immediately before its own children. Filtered by tailNumber this returns
// one airframe's full component tree in walk order; filtered by partNumber or
// serialNumber instead, it becomes a fleet-wide part search.
func (s *Server) handleSearchComponents(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	conds := []string{}
	args := []any{}
	if v := strings.TrimSpace(q.Get("tailNumber")); v != "" {
		conds = append(conds, "tail_number = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("category")); v != "" {
		conds = append(conds, "category = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("partNumber")); v != "" {
		conds = append(conds, "part_number = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("serialNumber")); v != "" {
		conds = append(conds, "UPPER(serial_number) LIKE ?")
		args = append(args, "%"+strings.ToUpper(v)+"%")
	}
	if len(conds) == 0 {
		writeError(w, http.StatusBadRequest, "bad_request",
			"at least one filter required (tailNumber, category, partNumber, serialNumber)")
		return
	}
	limit := 50
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("limit"))); err == nil && n > 0 && n <= 200 {
		limit = n
	}
	sqlStr := `SELECT component_id, tail_number, position_code, category, label,
	                  part_number, serial_number
	           FROM components WHERE ` + strings.Join(conds, " AND ") +
		" ORDER BY tail_number, position_code LIMIT ?"
	args = append(args, limit)
	rows, err := s.db.QueryContext(r.Context(), sqlStr, args...)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []model.ComponentSummary{}
	for rows.Next() {
		var it model.ComponentSummary
		if err := rows.Scan(&it.ComponentID, &it.TailNumber, &it.PositionCode, &it.Category,
			&it.Label, &it.PartNumber, &it.SerialNumber); err != nil {
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
		"count":      len(out),
		"limit":      limit,
		"components": out,
	})
}

// componentPatch represents a part change: a removal followed by an
// installation, recorded as one request. Pointers keep "absent from the body"
// distinguishable from "present and set to the empty string".
type componentPatch struct {
	PartNumber   *string `json:"partNumber"`
	SerialNumber *string `json:"serialNumber"`
	InstalledOn  *string `json:"installedOn"`
}

var partPattern = regexp.MustCompile(`^PN-\d{5}$`)
var serialPattern = regexp.MustCompile(`^SN-\d{7}$`)
var datePattern = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

// validateAndBuild returns the SET fragments and their bind arguments, or a
// bad-request message. A part swap resets the wear clock, so whenever
// partNumber or serialNumber changes, installedHours and installedCycles are
// pinned to the airframe's totals argument rather than left untouched — a new
// serial has never flown a single hour on this airframe yet.
func (p *componentPatch) validateAndBuild(af model.Airframe) ([]string, []any, string) {
	setParts := []string{}
	args := []any{}
	set := func(col string, val any) {
		setParts = append(setParts, col+" = ?")
		args = append(args, val)
	}
	swapped := false
	if p.PartNumber != nil {
		v := strings.TrimSpace(*p.PartNumber)
		if !partPattern.MatchString(v) {
			return nil, nil, "partNumber must match PN-NNNNN"
		}
		set("part_number", v)
		swapped = true
	}
	if p.SerialNumber != nil {
		v := strings.TrimSpace(*p.SerialNumber)
		if !serialPattern.MatchString(v) {
			return nil, nil, "serialNumber must match SN-NNNNNNN"
		}
		set("serial_number", v)
		swapped = true
	}
	if p.InstalledOn != nil {
		v := strings.TrimSpace(*p.InstalledOn)
		if !datePattern.MatchString(v) {
			return nil, nil, "installedOn must be YYYY-MM-DD"
		}
		set("installed_on", v)
	} else if swapped {
		set("installed_on", time.Now().UTC().Format("2006-01-02"))
	}
	if swapped {
		set("installed_hours", af.TotalHours)
		set("installed_cycles", af.TotalCycles)
	}
	return setParts, args, ""
}

func (s *Server) handlePatchComponent(w http.ResponseWriter, r *http.Request) {
	componentID := strings.TrimSpace(chi.URLParam(r, "componentId"))
	if ct := r.Header.Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		writeError(w, http.StatusBadRequest, "bad_request", "Content-Type must be application/json")
		return
	}
	var p componentPatch
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err.Error())
		return
	}
	current, err := s.loadComponent(r.Context(), componentID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "component not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	setParts, setArgs, badReq := p.validateAndBuild(*current.Airframe)
	if badReq != "" {
		writeError(w, http.StatusBadRequest, "bad_request", badReq)
		return
	}
	if len(setParts) == 0 {
		writeError(w, http.StatusBadRequest, "bad_request", "request body had no updatable fields")
		return
	}
	setArgs = append(setArgs, componentID)
	upd := fmt.Sprintf(`UPDATE components SET %s WHERE component_id = ?`, strings.Join(setParts, ", "))
	if _, err := s.db.ExecContext(r.Context(), upd, setArgs...); err != nil {
		s.serverError(w, err)
		return
	}
	updated, err := s.loadComponent(r.Context(), componentID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	compliance, err := s.loadCompliance(r.Context(), componentID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	updated.Compliance = compliance
	writeJSON(w, http.StatusOK, updated)
}
