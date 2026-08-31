package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"qsolog/internal/model"
)

// validBands and validModes are qsolog's band/mode pair: every contact, every
// confirmation, and every award-progress row is keyed by one member of each.
// Neither list is read from the database; a new band or mode is a code change.
var validBands = []string{"160m", "80m", "40m", "20m", "17m", "15m", "12m", "10m", "6m", "2m", "70cm"}
var validModes = []string{"CW", "SSB", "FM", "AM", "FT8", "RTTY", "PSK31"}

func validBand(v string) bool {
	for _, b := range validBands {
		if b == v {
			return true
		}
	}
	return false
}

func validMode(v string) bool {
	for _, m := range validModes {
		if m == v {
			return true
		}
	}
	return false
}

// loadContact pulls one logged contact and the station that logged it in one
// join. Nullable columns are coalesced so the scan targets can stay
// non-pointer, and callers get sql.ErrNoRows when the id does not resolve to a
// contact. Confirmations are left as an empty slice here; handleGetContact
// fills them in with a second query, the same shape stacks uses for loans.
func (s *Server) loadContact(ctx context.Context, contactID string) (model.Contact, error) {
	var c model.Contact
	var st model.Station
	err := s.db.QueryRowContext(ctx, `SELECT c.contact_id, c.station_id, c.worked_callsign,
	              c.band, c.mode, c.contact_date, c.contact_time,
	              COALESCE(c.signal_sent,''), COALESCE(c.signal_received,''),
	              COALESCE(c.grid_square,''), COALESCE(c.entity_code,''),
	              COALESCE(c.confirmed_on,''),
	              st.station_id, st.callsign, COALESCE(st.grid_square,''),
	              COALESCE(st.operator_class,'')
	       FROM contacts c
	       JOIN stations st ON st.station_id = c.station_id
	       WHERE c.contact_id = ?`, contactID).
		Scan(&c.ContactID, &c.StationID, &c.WorkedCallsign, &c.Band, &c.Mode,
			&c.ContactDate, &c.ContactTime, &c.SignalSent, &c.SignalReceived,
			&c.GridSquare, &c.EntityCode, &c.ConfirmedOn,
			&st.StationID, &st.Callsign, &st.GridSquare, &st.OperatorClass)
	if err != nil {
		return model.Contact{}, err
	}
	c.Station = &st
	c.Confirmations = []model.Confirmation{}
	return c, nil
}

// loadConfirmationsForContact reads the confirmation history matched against
// one contact, oldest first. Unmatched confirmations never carry a
// matched_contact_id, so they never surface here regardless of what they
// claimed.
func (s *Server) loadConfirmationsForContact(ctx context.Context, contactID string) ([]model.Confirmation, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT rowid, received_from, band, mode, contact_date,
	              match_status, logged_at
	       FROM confirmations WHERE matched_contact_id = ?
	       ORDER BY logged_at`, contactID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.Confirmation{}
	for rows.Next() {
		var cf model.Confirmation
		var id int64
		if err := rows.Scan(&id, &cf.ReceivedFrom, &cf.Band, &cf.Mode, &cf.ContactDate,
			&cf.MatchStatus, &cf.LoggedAt); err != nil {
			return nil, err
		}
		cf.ConfirmationID = strconv.FormatInt(id, 10)
		out = append(out, cf)
	}
	return out, rows.Err()
}

func (s *Server) handleGetContact(w http.ResponseWriter, r *http.Request) {
	contactID := strings.TrimSpace(chi.URLParam(r, "contactId"))
	c, err := s.loadContact(r.Context(), contactID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "contact not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	confirmations, err := s.loadConfirmationsForContact(r.Context(), contactID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	c.Confirmations = confirmations
	writeJSON(w, http.StatusOK, c)
}

type contactSummary struct {
	ContactID      string `json:"contactId"`
	StationID      string `json:"stationId"`
	WorkedCallsign string `json:"workedCallsign"`
	Band           string `json:"band"`
	Mode           string `json:"mode"`
	ContactDate    string `json:"contactDate"`
	EntityCode     string `json:"entityCode,omitempty"`
	Confirmed      bool   `json:"confirmed"`
}

// handleSearchContacts narrows the logbook by band, mode and a contact_date
// window; a station id restricts the search to one operator's own log. At
// least one filter is required so an empty query cannot walk the whole table.
func (s *Server) handleSearchContacts(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	conds := []string{}
	args := []any{}
	if v := strings.TrimSpace(q.Get("band")); v != "" {
		conds = append(conds, "band = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("mode")); v != "" {
		conds = append(conds, "mode = ?")
		args = append(args, strings.ToUpper(v))
	}
	if v := strings.TrimSpace(q.Get("stationId")); v != "" {
		conds = append(conds, "station_id = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("from")); v != "" {
		conds = append(conds, "contact_date >= ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("to")); v != "" {
		conds = append(conds, "contact_date <= ?")
		args = append(args, v)
	}
	if len(conds) == 0 {
		writeError(w, http.StatusBadRequest, "bad_request",
			"at least one filter required (band, mode, stationId, from, to)")
		return
	}
	limit := 50
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("limit"))); err == nil && n > 0 && n <= 200 {
		limit = n
	}
	sqlStr := `SELECT contact_id, station_id, worked_callsign, band, mode, contact_date,
	                  COALESCE(entity_code,''), confirmed_on IS NOT NULL
	           FROM contacts WHERE ` + strings.Join(conds, " AND ") +
		" ORDER BY contact_date DESC, contact_time DESC LIMIT ?"
	args = append(args, limit)
	rows, err := s.db.QueryContext(r.Context(), sqlStr, args...)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []contactSummary{}
	for rows.Next() {
		var it contactSummary
		if err := rows.Scan(&it.ContactID, &it.StationID, &it.WorkedCallsign, &it.Band,
			&it.Mode, &it.ContactDate, &it.EntityCode, &it.Confirmed); err != nil {
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
		"count":    len(out),
		"limit":    limit,
		"contacts": out,
	})
}

// confirmationRequest is the inbound claim: a station asserting it worked us on
// a given band, mode and date. It carries no contact id — finding the contact
// that matches it is the whole job of handleLogConfirmation.
type confirmationRequest struct {
	StationID    string `json:"stationId"`
	ReceivedFrom string `json:"receivedFrom"`
	Band         string `json:"band"`
	Mode         string `json:"mode"`
	ContactDate  string `json:"contactDate"`
}

type confirmationResult struct {
	ConfirmationID   string          `json:"confirmationId"`
	MatchStatus      string          `json:"matchStatus"`
	MatchedContactID string          `json:"matchedContactId,omitempty"`
	Contact          *contactSummary `json:"contact,omitempty"`
}

// handleLogConfirmation pairs an inbound confirmation against the logbook. A
// match requires the station, the worked callsign, the band, the mode and the
// contact date to agree exactly; there is no partial-credit fuzzy match. Every
// submission is recorded in the confirmations table regardless of outcome, so
// an operator can see what was claimed even when nothing lined up.
func (s *Server) handleLogConfirmation(w http.ResponseWriter, r *http.Request) {
	if ct := r.Header.Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		writeError(w, http.StatusBadRequest, "bad_request", "Content-Type must be application/json")
		return
	}
	var req confirmationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err.Error())
		return
	}
	req.StationID = strings.TrimSpace(req.StationID)
	req.ReceivedFrom = strings.ToUpper(strings.TrimSpace(req.ReceivedFrom))
	req.Band = strings.TrimSpace(req.Band)
	req.Mode = strings.ToUpper(strings.TrimSpace(req.Mode))
	req.ContactDate = strings.TrimSpace(req.ContactDate)
	if req.StationID == "" || req.ReceivedFrom == "" || req.ContactDate == "" {
		writeError(w, http.StatusBadRequest, "bad_request",
			"stationId, receivedFrom and contactDate are required")
		return
	}
	if !validBand(req.Band) {
		writeError(w, http.StatusBadRequest, "bad_request", "band is not recognised")
		return
	}
	if !validMode(req.Mode) {
		writeError(w, http.StatusBadRequest, "bad_request", "mode is not recognised")
		return
	}

	var contactID string
	err := s.db.QueryRowContext(r.Context(), `SELECT contact_id FROM contacts
	       WHERE station_id = ? AND worked_callsign = ? AND band = ? AND mode = ?
	             AND contact_date = ?`,
		req.StationID, req.ReceivedFrom, req.Band, req.Mode, req.ContactDate).Scan(&contactID)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		s.serverError(w, err)
		return
	}

	res := confirmationResult{MatchStatus: "unmatched"}
	if contactID != "" {
		res.MatchStatus = "matched"
		res.MatchedContactID = contactID
		if _, err := s.db.ExecContext(r.Context(),
			`UPDATE contacts SET confirmed_on = ? WHERE contact_id = ? AND confirmed_on IS NULL`,
			req.ContactDate, contactID); err != nil {
			s.serverError(w, err)
			return
		}
		c, err := s.loadContact(r.Context(), contactID)
		if err != nil {
			s.serverError(w, err)
			return
		}
		res.Contact = &contactSummary{ContactID: c.ContactID, StationID: c.StationID,
			WorkedCallsign: c.WorkedCallsign, Band: c.Band, Mode: c.Mode,
			ContactDate: c.ContactDate, EntityCode: c.EntityCode, Confirmed: true}
	}

	confirmationID, err := s.insertConfirmation(r.Context(), req, res.MatchStatus, contactID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	res.ConfirmationID = confirmationID
	status := http.StatusOK
	if res.MatchStatus == "unmatched" {
		status = http.StatusAccepted
	}
	writeJSON(w, status, res)
}

// insertConfirmation writes the audit row. matchedContactID may be empty; the
// column is nullable for exactly that case. logged_at is stamped by SQLite,
// not by this process's clock, so a batch of submissions replayed later still
// carries the time they were actually recorded.
func (s *Server) insertConfirmation(ctx context.Context, req confirmationRequest,
	matchStatus, matchedContactID string) (string, error) {
	var matched any
	if matchedContactID != "" {
		matched = matchedContactID
	}
	res, err := s.db.ExecContext(ctx, `INSERT INTO confirmations
	       (station_id, received_from, band, mode, contact_date, match_status,
	        matched_contact_id, logged_at)
	       VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))`,
		req.StationID, req.ReceivedFrom, req.Band, req.Mode, req.ContactDate, matchStatus, matched)
	if err != nil {
		return "", err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return "", err
	}
	return strconv.FormatInt(id, 10), nil
}

type bandModeProgress struct {
	Band              string `json:"band"`
	Mode              string `json:"mode"`
	ConfirmedContacts int    `json:"confirmedContacts"`
	DistinctEntities  int    `json:"distinctEntities"`
}

// handleAwardProgress rolls confirmed contacts up by band/mode pair and counts
// the distinct entity codes each pair has reached. It is the only handler in
// this file that answers a "how close" question rather than a "what happened"
// one: award credit is this count, not a row anywhere in the schema. Entity
// codes come from qsolog's own invented entity list, never a real award
// program's country or territory list.
func (s *Server) handleAwardProgress(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	conds := []string{"confirmed_on IS NOT NULL"}
	args := []any{}
	if v := strings.TrimSpace(q.Get("stationId")); v != "" {
		conds = append(conds, "station_id = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("band")); v != "" {
		conds = append(conds, "band = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("mode")); v != "" {
		conds = append(conds, "mode = ?")
		args = append(args, strings.ToUpper(v))
	}
	sqlStr := `SELECT band, mode, count(*), count(DISTINCT entity_code)
	           FROM contacts WHERE ` + strings.Join(conds, " AND ") +
		` GROUP BY band, mode ORDER BY band, mode`
	rows, err := s.db.QueryContext(r.Context(), sqlStr, args...)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []bandModeProgress{}
	for rows.Next() {
		var p bandModeProgress
		if err := rows.Scan(&p.Band, &p.Mode, &p.ConfirmedContacts, &p.DistinctEntities); err != nil {
			s.serverError(w, err)
			return
		}
		out = append(out, p)
	}
	if err := rows.Err(); err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"progress": out})
}
