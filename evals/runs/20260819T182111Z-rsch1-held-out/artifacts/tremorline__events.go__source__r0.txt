package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"

	"tremorline/internal/model"
)

// loadEvent pulls one catalog row. Magnitude is nullable in storage until an
// association run has computed one, which is why the scan target is a
// sql.NullFloat64 rather than a bare float64.
func (s *Server) loadEvent(ctx context.Context, eventID string) (model.Event, error) {
	var e model.Event
	var mag sql.NullFloat64
	var magType sql.NullString
	err := s.db.QueryRowContext(ctx, `SELECT event_id, origin_time, latitude, longitude,
	              depth_km, magnitude, magnitude_type, review_status, detection_count
	       FROM events WHERE event_id = ?`, eventID).
		Scan(&e.EventID, &e.OriginTime, &e.Latitude, &e.Longitude, &e.DepthKm,
			&mag, &magType, &e.ReviewStatus, &e.DetectionCount)
	if err != nil {
		return model.Event{}, err
	}
	if mag.Valid {
		e.Magnitude = mag.Float64
	}
	if magType.Valid {
		e.MagnitudeType = magType.String
	}
	return e, nil
}

func (s *Server) loadEstimatesForEvent(ctx context.Context, eventID string) ([]model.MagnitudeEstimate, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT estimate_id, event_id, channel_id, value,
	                  mag_type, residual
	           FROM magnitude_estimates WHERE event_id = ? ORDER BY estimate_id`, eventID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.MagnitudeEstimate{}
	for rows.Next() {
		var m model.MagnitudeEstimate
		if err := rows.Scan(&m.EstimateID, &m.EventID, &m.ChannelID, &m.Value,
			&m.MagType, &m.Residual); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

func (s *Server) loadDetectionsForEvent(ctx context.Context, eventID string) ([]model.Detection, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT detection_id, channel_id, station_id,
	                  detected_at, amplitude, COALESCE(period_s, 0), COALESCE(phase_hint,''),
	                  COALESCE(event_id,'')
	           FROM detections WHERE event_id = ? ORDER BY detected_at`, eventID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.Detection{}
	for rows.Next() {
		var d model.Detection
		if err := rows.Scan(&d.DetectionID, &d.ChannelID, &d.StationID, &d.DetectedAt,
			&d.Amplitude, &d.PeriodS, &d.PhaseHint, &d.EventID); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

func (s *Server) handleGetEvent(w http.ResponseWriter, r *http.Request) {
	eventID := strings.TrimSpace(chi.URLParam(r, "eventId"))
	e, err := s.loadEvent(r.Context(), eventID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "event not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	estimates, err := s.loadEstimatesForEvent(r.Context(), eventID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	detections, err := s.loadDetectionsForEvent(r.Context(), eventID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	e.Estimates = estimates
	e.Detections = detections
	writeJSON(w, http.StatusOK, e)
}

type eventSummary struct {
	EventID       string  `json:"eventId"`
	OriginTime    string  `json:"originTime"`
	Latitude      float64 `json:"latitude"`
	Longitude     float64 `json:"longitude"`
	DepthKm       float64 `json:"depthKm"`
	Magnitude     float64 `json:"magnitude,omitempty"`
	MagnitudeType string  `json:"magnitudeType,omitempty"`
	ReviewStatus  string  `json:"reviewStatus"`
}

// handleSearchEvents answers the catalog query. Unlike a filter panel where
// every field is optional, an event search here is meaningless without all
// three bounds at once: a bare time window over a whole regional array
// returns thousands of rows, and a bare magnitude range with no window or box
// is a full-table scan by another name. The three groups are required
// together, not composed a la carte.
func (s *Server) handleSearchEvents(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	from := strings.TrimSpace(q.Get("from"))
	to := strings.TrimSpace(q.Get("to"))
	if from == "" || to == "" {
		writeError(w, http.StatusBadRequest, "bad_request", "from and to (RFC3339) are both required")
		return
	}
	if _, err := time.Parse(time.RFC3339, from); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", "from must be RFC3339")
		return
	}
	if _, err := time.Parse(time.RFC3339, to); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", "to must be RFC3339")
		return
	}
	minMag, errMin := strconv.ParseFloat(strings.TrimSpace(q.Get("minMagnitude")), 64)
	maxMag, errMax := strconv.ParseFloat(strings.TrimSpace(q.Get("maxMagnitude")), 64)
	if errMin != nil || errMax != nil {
		writeError(w, http.StatusBadRequest, "bad_request", "minMagnitude and maxMagnitude are both required")
		return
	}
	minLat, e1 := strconv.ParseFloat(strings.TrimSpace(q.Get("minLat")), 64)
	maxLat, e2 := strconv.ParseFloat(strings.TrimSpace(q.Get("maxLat")), 64)
	minLon, e3 := strconv.ParseFloat(strings.TrimSpace(q.Get("minLon")), 64)
	maxLon, e4 := strconv.ParseFloat(strings.TrimSpace(q.Get("maxLon")), 64)
	if e1 != nil || e2 != nil || e3 != nil || e4 != nil {
		writeError(w, http.StatusBadRequest, "bad_request", "minLat, maxLat, minLon and maxLon are all required")
		return
	}
	limit := 50
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("limit"))); err == nil && n > 0 && n <= 200 {
		limit = n
	}
	rows, err := s.db.QueryContext(r.Context(), `SELECT event_id, origin_time, latitude,
	                  longitude, depth_km, COALESCE(magnitude, 0), COALESCE(magnitude_type,''),
	                  review_status
	           FROM events
	           WHERE origin_time >= ? AND origin_time <= ?
	             AND COALESCE(magnitude, 0) BETWEEN ? AND ?
	             AND latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
	           ORDER BY origin_time DESC LIMIT ?`,
		from, to, minMag, maxMag, minLat, maxLat, minLon, maxLon, limit)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []eventSummary{}
	for rows.Next() {
		var ev eventSummary
		if err := rows.Scan(&ev.EventID, &ev.OriginTime, &ev.Latitude, &ev.Longitude,
			&ev.DepthKm, &ev.Magnitude, &ev.MagnitudeType, &ev.ReviewStatus); err != nil {
			s.serverError(w, err)
			return
		}
		out = append(out, ev)
	}
	if err := rows.Err(); err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"count":  len(out),
		"limit":  limit,
		"events": out,
	})
}

// haversineKm is the great-circle distance between two lat/long points, used
// only to turn a raw amplitude reading into a distance-corrected magnitude
// estimate. It has no relationship to any survey-grade geodesy library; a
// spherical-earth approximation is what the association handler needs.
func haversineKm(lat1, lon1, lat2, lon2 float64) float64 {
	const earthRadiusKm = 6371.0
	rad := func(d float64) float64 { return d * math.Pi / 180 }
	dLat := rad(lat2 - lat1)
	dLon := rad(lon2 - lon1)
	a := math.Sin(dLat/2)*math.Sin(dLat/2) +
		math.Cos(rad(lat1))*math.Cos(rad(lat2))*math.Sin(dLon/2)*math.Sin(dLon/2)
	return earthRadiusKm * 2 * math.Atan2(math.Sqrt(a), math.Sqrt(1-a))
}

// localMagnitude is a simplified log-amplitude estimate with a distance
// correction term. It exists to give each station a per-channel estimate to
// average, not to be a defensible scale definition.
func localMagnitude(amplitude, distanceKm float64) float64 {
	if amplitude <= 0 {
		amplitude = 1e-9
	}
	if distanceKm <= 0 {
		distanceKm = 1
	}
	return math.Log10(amplitude) + 3*math.Log10(distanceKm) - 2.92
}

type associateRequest struct {
	DetectionIDs []string `json:"detectionIds"`
	OriginTime   string   `json:"originTime"`
	Latitude     float64  `json:"latitude"`
	Longitude    float64  `json:"longitude"`
	DepthKm      float64  `json:"depthKm"`
}

type detectionRow struct {
	detectionID, channelID, stationID string
	amplitude                         float64
	eventID                           string
	stationLat, stationLon            float64
}

// handleAssociateDetections is the cross-station grouping step: given a
// candidate origin and a set of currently unassociated detections, it
// confirms the detections span more than one station (a single station
// reporting a transient is not an event), computes one magnitude estimate
// per detection from its station's distance to the proposed origin, and
// writes a new event row that the detections are then bound to.
func (s *Server) handleAssociateDetections(w http.ResponseWriter, r *http.Request) {
	if ct := r.Header.Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		writeError(w, http.StatusBadRequest, "bad_request", "Content-Type must be application/json")
		return
	}
	var req associateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err.Error())
		return
	}
	if len(req.DetectionIDs) < 2 {
		writeError(w, http.StatusBadRequest, "bad_request", "at least two detectionIds are required")
		return
	}
	if _, err := time.Parse(time.RFC3339, strings.TrimSpace(req.OriginTime)); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", "originTime must be RFC3339")
		return
	}

	ctx := r.Context()
	stations := map[string]bool{}
	rowsIn := make([]detectionRow, 0, len(req.DetectionIDs))
	for _, id := range req.DetectionIDs {
		var d detectionRow
		var existingEvent sql.NullString
		err := s.db.QueryRowContext(ctx, `SELECT d.detection_id, d.channel_id, d.station_id,
		              d.amplitude, d.event_id, s.latitude, s.longitude
		       FROM detections d JOIN stations s ON s.station_id = d.station_id
		       WHERE d.detection_id = ?`, id).
			Scan(&d.detectionID, &d.channelID, &d.stationID, &d.amplitude,
				&existingEvent, &d.stationLat, &d.stationLon)
		if errors.Is(err, sql.ErrNoRows) {
			writeError(w, http.StatusNotFound, "not_found", "detection not found: "+id)
			return
		}
		if err != nil {
			s.serverError(w, err)
			return
		}
		if existingEvent.Valid && existingEvent.String != "" {
			writeError(w, http.StatusConflict, "already_associated",
				"detection already belongs to an event: "+id)
			return
		}
		stations[d.stationID] = true
		rowsIn = append(rowsIn, d)
	}
	if len(stations) < 2 {
		writeError(w, http.StatusBadRequest, "bad_request",
			"detections must span at least two stations to form an event")
		return
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer tx.Rollback()

	var eventID string
	if err := tx.QueryRowContext(ctx,
		`SELECT 'RRA-EVT-' || substr('000000' || (count(*) + 1), -6, 6) FROM events`).
		Scan(&eventID); err != nil {
		s.serverError(w, err)
		return
	}
	if _, err := tx.ExecContext(ctx,
		`INSERT INTO events (event_id, origin_time, latitude, longitude, depth_km,
		        review_status, detection_count)
		 VALUES (?, ?, ?, ?, ?, 'automatic', ?)`,
		eventID, req.OriginTime, req.Latitude, req.Longitude, req.DepthKm, len(rowsIn)); err != nil {
		s.serverError(w, err)
		return
	}

	sum := 0.0
	for i, d := range rowsIn {
		distKm := haversineKm(req.Latitude, req.Longitude, d.stationLat, d.stationLon)
		mag := localMagnitude(d.amplitude, distKm)
		sum += mag
		estimateID := eventID + "-M" + strconv.Itoa(i+1)
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO magnitude_estimates (estimate_id, event_id, channel_id, value,
			        mag_type, residual) VALUES (?, ?, ?, ?, 'ML', 0)`,
			estimateID, eventID, d.channelID, mag); err != nil {
			s.serverError(w, err)
			return
		}
		if _, err := tx.ExecContext(ctx,
			`UPDATE detections SET event_id = ? WHERE detection_id = ?`,
			eventID, d.detectionID); err != nil {
			s.serverError(w, err)
			return
		}
	}
	avgMag := sum / float64(len(rowsIn))
	if _, err := tx.ExecContext(ctx,
		`UPDATE events SET magnitude = ?, magnitude_type = 'ML' WHERE event_id = ?`,
		avgMag, eventID); err != nil {
		s.serverError(w, err)
		return
	}
	if err := tx.Commit(); err != nil {
		s.serverError(w, err)
		return
	}

	e, err := s.loadEvent(ctx, eventID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	estimates, err := s.loadEstimatesForEvent(ctx, eventID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	detections, err := s.loadDetectionsForEvent(ctx, eventID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	e.Estimates = estimates
	e.Detections = detections
	writeJSON(w, http.StatusCreated, e)
}
