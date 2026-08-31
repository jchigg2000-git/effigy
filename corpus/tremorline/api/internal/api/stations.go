package api

import (
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"

	"tremorline/internal/model"
)

type stationSummary struct {
	StationID    string `json:"stationId"`
	NetworkCode  string `json:"networkCode"`
	Name         string `json:"name"`
	Status       string `json:"status"`
	ChannelCount int    `json:"channelCount"`
}

// handleListStations answers the inventory roster, one row per station with a
// live count of its channel-epoch rows. networkCode and status are the only
// filters; a full station list at array scale is small enough that neither
// one is required the way the event search's bounds are.
func (s *Server) handleListStations(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	conds := []string{}
	args := []any{}
	if v := strings.TrimSpace(q.Get("networkCode")); v != "" {
		conds = append(conds, "st.network_code = ?")
		args = append(args, strings.ToUpper(v))
	}
	if v := strings.TrimSpace(q.Get("status")); v != "" {
		conds = append(conds, "st.status = ?")
		args = append(args, strings.ToUpper(v))
	}
	where := ""
	if len(conds) > 0 {
		where = "WHERE " + strings.Join(conds, " AND ")
	}
	rows, err := s.db.QueryContext(r.Context(), `SELECT st.station_id, st.network_code,
	                  st.name, st.status, count(c.channel_id)
	           FROM stations st LEFT JOIN channels c ON c.station_id = st.station_id
	           `+where+`
	           GROUP BY st.station_id ORDER BY st.station_id`, args...)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []stationSummary{}
	for rows.Next() {
		var st stationSummary
		if err := rows.Scan(&st.StationID, &st.NetworkCode, &st.Name, &st.Status,
			&st.ChannelCount); err != nil {
			s.serverError(w, err)
			return
		}
		out = append(out, st)
	}
	if err := rows.Err(); err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"count":    len(out),
		"stations": out,
	})
}

// handleGetStationInventory returns one station and every epoch of every
// channel it has ever carried, oldest validity window first. A channel that
// was recalibrated shows up as more than one entry sharing channelCode.
func (s *Server) handleGetStationInventory(w http.ResponseWriter, r *http.Request) {
	stationID := strings.TrimSpace(chi.URLParam(r, "stationId"))
	var st model.Station
	err := s.db.QueryRowContext(r.Context(), `SELECT station_id, network_code, name,
	              latitude, longitude, elevation_m, operator, status
	       FROM stations WHERE station_id = ?`, stationID).
		Scan(&st.StationID, &st.NetworkCode, &st.Name, &st.Latitude, &st.Longitude,
			&st.ElevationM, &st.Operator, &st.Status)
	if err != nil {
		writeError(w, http.StatusNotFound, "not_found", "station not found")
		return
	}
	rows, err := s.db.QueryContext(r.Context(), `SELECT channel_id, station_id, channel_code,
	                  sample_rate_hz, azimuth_deg, dip_deg, depth_m, validity_start,
	                  COALESCE(validity_end,'')
	           FROM channels WHERE station_id = ?
	           ORDER BY channel_code, validity_start`, stationID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	channels := []model.Channel{}
	for rows.Next() {
		var c model.Channel
		if err := rows.Scan(&c.ChannelID, &c.StationID, &c.ChannelCode, &c.SampleRateHz,
			&c.AzimuthDeg, &c.DipDeg, &c.DepthM, &c.ValidityStart, &c.ValidityEnd); err != nil {
			s.serverError(w, err)
			return
		}
		channels = append(channels, c)
	}
	if err := rows.Err(); err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"station":  st,
		"channels": channels,
	})
}
