package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"meterworks/internal/model"
)

// loadRead pulls one read together with the service point and meter it was
// taken against. Six columns come from reads, three from service_points and
// three from meters, in the order the SELECT list declares them.
func (s *Server) loadRead(ctx context.Context, readID string) (model.Read, error) {
	var rd model.Read
	var sp model.ServicePoint
	var mt model.Meter
	err := s.db.QueryRowContext(ctx, `SELECT r.read_id, r.meter_id, r.service_point_id,
	              r.route_code, r.cycle_code, r.read_type, r.read_value, r.read_date,
	              r.tolerance_flag, COALESCE(r.exception_reason,''),
	              sp.service_point_id, sp.route_code, COALESCE(sp.account_ref,''),
	              m.meter_id, m.serial_number, COALESCE(m.size_code,'')
	       FROM reads r
	       JOIN service_points sp ON sp.service_point_id = r.service_point_id
	       JOIN meters m ON m.meter_id = r.meter_id
	       WHERE r.read_id = ?`, readID).Scan(&rd.ReadID, &rd.MeterID, &rd.ServicePointID,
		&rd.RouteCode, &rd.CycleCode, &rd.ReadType, &rd.ReadValue, &rd.ReadDate,
		&rd.ToleranceFlag, &rd.ExceptionReason,
		&sp.ServicePointID, &sp.RouteCode, &sp.AccountRef,
		&mt.MeterID, &mt.SerialNumber, &mt.SizeCode)
	if err != nil {
		return model.Read{}, err
	}
	sp.Meter = &mt
	rd.ServicePoint = &sp
	return rd, nil
}

// priorRead finds the most recent trusted reading on the same meter, taken
// before this one. Estimated reads are skipped: they carry no register
// value the tiered calculation can build an interval from.
func (s *Server) priorRead(ctx context.Context, meterID, readID, readDate string) (string, int, bool) {
	var id string
	var value int
	err := s.db.QueryRowContext(ctx, `SELECT read_id, read_value FROM reads
	       WHERE meter_id = ? AND read_id != ? AND read_date < ? AND read_type != 'ESTIMATED'
	       ORDER BY read_date DESC LIMIT 1`, meterID, readID, readDate).Scan(&id, &value)
	if err != nil {
		return "", 0, false
	}
	return id, value, true
}

func (s *Server) rateTiers(ctx context.Context, cycleCode string) ([]model.RateTier, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT tier_number, COALESCE(upper_units,0),
	              rate_cents_per_unit FROM rate_tiers WHERE cycle_code = ?
	       ORDER BY tier_number`, cycleCode)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.RateTier{}
	for rows.Next() {
		var t model.RateTier
		if err := rows.Scan(&t.TierNumber, &t.UpperUnits, &t.RateCentsPerUnit); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

// computeTieredCharge walks the rate schedule in tier order and accumulates
// a charge in cents. Each tier absorbs the portion of usage between the
// previous tier's threshold and its own; a tier whose UpperUnits is zero is
// the open-ended top tier and absorbs everything still unclaimed.
func computeTieredCharge(usageUnits int, tiers []model.RateTier) int {
	if usageUnits <= 0 {
		return 0
	}
	total := 0
	lower := 0
	for _, t := range tiers {
		upper := t.UpperUnits
		if upper == 0 || upper > usageUnits {
			upper = usageUnits
		}
		if span := upper - lower; span > 0 {
			total += span * t.RateCentsPerUnit
		}
		lower = upper
		if lower >= usageUnits {
			break
		}
	}
	return total
}

func (s *Server) handleGetRead(w http.ResponseWriter, r *http.Request) {
	readID := strings.TrimSpace(chi.URLParam(r, "readId"))
	rd, err := s.loadRead(r.Context(), readID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "read not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	if priorID, priorValue, ok := s.priorRead(r.Context(), rd.MeterID, rd.ReadID, rd.ReadDate); ok {
		tiers, err := s.rateTiers(r.Context(), rd.CycleCode)
		if err != nil {
			s.serverError(w, err)
			return
		}
		units := rd.ReadValue - priorValue
		rd.Consumption = &model.Consumption{
			PriorReadID: priorID,
			UnitsUsed:   units,
			ChargeCents: computeTieredCharge(units, tiers),
		}
	}
	writeJSON(w, http.StatusOK, rd)
}

type readSummary struct {
	ReadID         string `json:"readId"`
	ServicePointID string `json:"servicePointId"`
	MeterID        string `json:"meterId"`
	ReadType       string `json:"readType"`
	ReadValue      int    `json:"readValue"`
	ReadDate       string `json:"readDate"`
	ToleranceFlag  bool   `json:"toleranceFlag"`
}

// handleListRouteReads pages the reads taken along one meter-reading route.
// There is no routes table to check the code against — a route is a
// property of the service points assigned to it, not a first-class row — so
// an unrecognised route simply pages to zero results rather than 404ing.
func (s *Server) handleListRouteReads(w http.ResponseWriter, r *http.Request) {
	routeCode := strings.TrimSpace(chi.URLParam(r, "routeCode"))
	q := r.URL.Query()
	limit := 50
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("limit"))); err == nil && n > 0 && n <= 500 {
		limit = n
	}
	offset := 0
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("offset"))); err == nil && n > 0 {
		offset = n
	}
	cycleCode := strings.TrimSpace(q.Get("cycleCode"))

	sqlStr := `SELECT read_id, service_point_id, meter_id, read_type, read_value,
	                  read_date, tolerance_flag
	           FROM reads WHERE route_code = ?`
	args := []any{routeCode}
	if cycleCode != "" {
		sqlStr += " AND cycle_code = ?"
		args = append(args, cycleCode)
	}
	sqlStr += " ORDER BY read_date DESC, read_id LIMIT ? OFFSET ?"
	args = append(args, limit, offset)

	rows, err := s.db.QueryContext(r.Context(), sqlStr, args...)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []readSummary{}
	for rows.Next() {
		var it readSummary
		if err := rows.Scan(&it.ReadID, &it.ServicePointID, &it.MeterID, &it.ReadType,
			&it.ReadValue, &it.ReadDate, &it.ToleranceFlag); err != nil {
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
		"routeCode": routeCode,
		"count":     len(out),
		"limit":     limit,
		"offset":    offset,
		"reads":     out,
	})
}

// exceptionPatch carries pointers so that "absent from the body" stays
// distinguishable from "present and set to false/empty". requeue is the
// only field that triggers a write beyond the flagged read itself: it opens
// a fresh RE-READ record so a field crew has something to close out against.
type exceptionPatch struct {
	ToleranceFlag *bool   `json:"toleranceFlag"`
	Reason        *string `json:"reason"`
	Requeue       *bool   `json:"requeue"`
}

var reasonPattern = regexp.MustCompile(`^(OUT_OF_TOLERANCE|METER_STUCK|ACCESS_BLOCKED|TRANSCRIPTION_ERROR)$`)

func (p *exceptionPatch) validate() string {
	if p.Reason != nil && *p.Reason != "" && !reasonPattern.MatchString(*p.Reason) {
		return "reason must be one of OUT_OF_TOLERANCE, METER_STUCK, ACCESS_BLOCKED, TRANSCRIPTION_ERROR"
	}
	return ""
}

func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// handleReadException flags or clears a read as outside tolerance and,
// optionally, requeues it: rather than mutating the register value in
// place, requeuing inserts a new pending RE-READ row against the same meter
// so a field crew can supply a fresh, trusted number. The original read is
// never deleted; it stays as the exception record of what was first seen.
func (s *Server) handleReadException(w http.ResponseWriter, r *http.Request) {
	readID := strings.TrimSpace(chi.URLParam(r, "readId"))
	var p exceptionPatch
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err.Error())
		return
	}
	if msg := p.validate(); msg != "" {
		writeError(w, http.StatusBadRequest, "bad_request", msg)
		return
	}
	rd, err := s.loadRead(r.Context(), readID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "read not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}

	tolerance := rd.ToleranceFlag
	if p.ToleranceFlag != nil {
		tolerance = *p.ToleranceFlag
	}
	reason := rd.ExceptionReason
	if p.Reason != nil {
		reason = *p.Reason
	}
	if _, err := s.db.ExecContext(r.Context(),
		`UPDATE reads SET tolerance_flag = ?, exception_reason = ? WHERE read_id = ?`,
		tolerance, nullStr(reason), readID); err != nil {
		s.serverError(w, err)
		return
	}

	if p.Requeue != nil && *p.Requeue {
		newID := readID + "-RQ"
		if _, err := s.db.ExecContext(r.Context(),
			`INSERT INTO reads (read_id, meter_id, service_point_id, route_code, cycle_code,
			        read_type, read_value, read_date, tolerance_flag)
			 VALUES (?, ?, ?, ?, ?, 'RE-READ', 0, ?, 0)`,
			newID, rd.MeterID, rd.ServicePointID, rd.RouteCode, rd.CycleCode, rd.ReadDate); err != nil {
			s.serverError(w, err)
			return
		}
	}

	updated, err := s.loadRead(r.Context(), readID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, updated)
}
