// looms.go holds the loom resource, the smaller of the two — a plain lookup
// plus a utilisation rollup aggregated across a date range.
package api

import (
	"database/sql"
	"errors"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"

	"loomshed/internal/model"
)

// handleGetLoom returns a loom's fixed attributes. loomType is one of the
// mill's four weaving technologies — rapier, airjet, waterjet, shuttle — and
// widthCm is the reed width the loom is dressed to, not the fabric's
// finished width after any take-up.
func (s *Server) handleGetLoom(w http.ResponseWriter, r *http.Request) {
	loomID := strings.TrimSpace(chi.URLParam(r, "loomId"))
	var l model.LoomRef
	var widthCM int
	err := s.db.QueryRowContext(r.Context(), `SELECT loom_id, COALESCE(name,''),
	              COALESCE(loom_type,''), COALESCE(width_cm,0)
	       FROM looms WHERE loom_id = ?`, loomID).
		Scan(&l.LoomID, &l.Name, &l.LoomType, &widthCM)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "loom not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"loomId":   l.LoomID,
		"name":     l.Name,
		"loomType": l.LoomType,
		"widthCm":  widthCM,
	})
}

// shiftMinutes is the length of one logged shift. It is a constant rather
// than a column because every shift at this mill runs the same length; a
// mill that varied it would need to carry it on the shift row instead.
const shiftMinutes = 480

// handleLoomUtilisation aggregates every shift run against a loom within
// [from, to] into a single rollup: total metres woven, total downtime, how
// many shifts contributed, and the derived uptime percentage. Unlike the
// run detail path, this never touches the runs or defects tables at all —
// the shift rows carry everything the rollup needs.
func (s *Server) handleLoomUtilisation(w http.ResponseWriter, r *http.Request) {
	loomID := strings.TrimSpace(chi.URLParam(r, "loomId"))
	from := strings.TrimSpace(r.URL.Query().Get("from"))
	to := strings.TrimSpace(r.URL.Query().Get("to"))
	if from == "" || to == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "from and to are both required")
		return
	}
	var probe string
	err := s.db.QueryRowContext(r.Context(),
		`SELECT loom_id FROM looms WHERE loom_id = ?`, loomID).Scan(&probe)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "loom not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	var outputTotal float64
	var downtimeTotal int64
	var shiftCount int
	err = s.db.QueryRowContext(r.Context(), `SELECT COALESCE(SUM(so.output_m),0),
	              COALESCE(SUM(so.downtime_min),0), COUNT(*)
	       FROM shift_outputs so
	       JOIN runs r ON r.run_id = so.run_id
	       WHERE r.loom_id = ? AND so.shift_date >= ? AND so.shift_date <= ?`,
		loomID, from, to).Scan(&outputTotal, &downtimeTotal, &shiftCount)
	if err != nil {
		s.serverError(w, err)
		return
	}
	uptimePct := 0.0
	if shiftCount > 0 {
		scheduled := float64(shiftCount * shiftMinutes)
		uptimePct = 100 * (1 - float64(downtimeTotal)/scheduled)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"loomId":           loomID,
		"from":             from,
		"to":               to,
		"shiftsCounted":    shiftCount,
		"outputTotalM":     outputTotal,
		"downtimeTotalMin": downtimeTotal,
		"uptimePct":        uptimePct,
	})
}
