// Package ingest reads the RRA Channel Metadata Exchange format (.rcm) — a
// local profile invented for this array, not SEED, not StationXML, not any
// published exchange format. A file is a sequence of station blocks. Each
// block opens with a STA line and a run of KEY value lines describing the
// station, then zero or more CHAN blocks describing one channel each. A CHAN
// block carries its instrument geometry and one or more EPOCH lines, each
// naming a validity window; a channel recalibrated mid-deployment gets a
// second EPOCH line rather than a second CHAN line. A block closes on an
// explicit END line, which is what separates records — blank lines and '#'
// comment lines are ignored wherever they appear and carry no structural
// meaning.
package ingest

import (
	"context"
	"database/sql"
	"os"
	"strconv"
	"strings"
)

type Counts struct {
	Stations int `json:"stations"`
	Channels int `json:"channels"`
}

// epoch is one validity window for a channel. End is empty for "OPEN", the
// window still in force.
type epoch struct {
	Start, End string
}

type parsedChannel struct {
	Code                               string
	RateHz, AzimuthDeg, DipDeg, DepthM float64
	Epochs                             []epoch
}

type parsedStation struct {
	StationID, NetworkCode, Name, Operator, Status string
	Latitude, Longitude, ElevationM                float64
	Channels                                       []parsedChannel
}

func parseFloatOr(s string, fallback float64) float64 {
	v, err := strconv.ParseFloat(strings.TrimSpace(s), 64)
	if err != nil {
		return fallback
	}
	return v
}

func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// splitKV separates a line into its leading key and the rest of the line,
// which may itself contain internal whitespace (station and operator names
// are free text).
func splitKV(line string) (string, string) {
	parts := strings.SplitN(strings.TrimSpace(line), " ", 2)
	key := parts[0]
	val := ""
	if len(parts) == 2 {
		val = strings.TrimSpace(parts[1])
	}
	return key, val
}

// Parse walks the file a line at a time. The station and channel under
// construction are held in this scope and mutated from inside the key
// switch; flushChannel and flushStation take no arguments and read those
// variables directly, so a case arm closes a record blind.
func Parse(data []byte) []parsedStation {
	var out []parsedStation
	var cur *parsedStation
	var curChan *parsedChannel

	flushChannel := func() {
		if cur != nil && curChan != nil && curChan.Code != "" {
			cur.Channels = append(cur.Channels, *curChan)
		}
		curChan = nil
	}
	flushStation := func() {
		flushChannel()
		if cur != nil && cur.StationID != "" {
			out = append(out, *cur)
		}
		cur = nil
	}

	for _, raw := range strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, val := splitKV(line)
		switch key {
		case "STA":
			flushStation()
			cur = &parsedStation{StationID: val, Status: "ACTIVE"}
		case "END":
			flushStation()
		}
		if cur == nil {
			continue
		}
		switch key {
		case "NET":
			cur.NetworkCode = strings.ToUpper(val)
		case "NAME":
			cur.Name = val
		case "LAT":
			cur.Latitude = parseFloatOr(val, 0)
		case "LON":
			cur.Longitude = parseFloatOr(val, 0)
		case "ELEV":
			cur.ElevationM = parseFloatOr(val, 0)
		case "OPERATOR":
			cur.Operator = val
		case "STATUS":
			cur.Status = strings.ToUpper(val)
		case "CHAN":
			flushChannel()
			curChan = &parsedChannel{Code: val}
		}
		if curChan == nil {
			continue
		}
		switch key {
		case "RATE":
			curChan.RateHz = parseFloatOr(val, 0)
		case "AZIMUTH":
			curChan.AzimuthDeg = parseFloatOr(val, 0)
		case "DIP":
			curChan.DipDeg = parseFloatOr(val, 0)
		case "DEPTH":
			curChan.DepthM = parseFloatOr(val, 0)
		case "EPOCH":
			fields := strings.Fields(val)
			if len(fields) == 0 {
				continue
			}
			e := epoch{Start: fields[0]}
			if len(fields) > 1 && fields[1] != "OPEN" {
				e.End = fields[1]
			}
			curChan.Epochs = append(curChan.Epochs, e)
		}
	}
	flushStation()
	return out
}

// FromFile reloads the whole station-channel inventory from one seed file
// inside a transaction. A channel with N epochs becomes N channel rows,
// sharing channel_code but not channel_id, one row per validity window.
func FromFile(ctx context.Context, db *sql.DB, path string) (Counts, error) {
	var c Counts
	data, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	stations := Parse(data)
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return c, err
	}
	defer tx.Rollback()
	for _, t := range []string{"channels", "stations"} {
		if _, err := tx.ExecContext(ctx, "DELETE FROM "+t); err != nil {
			return c, err
		}
	}
	for _, st := range stations {
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO stations (station_id, network_code, name, latitude, longitude,
			        elevation_m, operator, status)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			st.StationID, nullStr(st.NetworkCode), st.Name, st.Latitude, st.Longitude,
			st.ElevationM, nullStr(st.Operator), st.Status); err != nil {
			return c, err
		}
		c.Stations++
		for _, ch := range st.Channels {
			if len(ch.Epochs) == 0 {
				continue
			}
			for i, ep := range ch.Epochs {
				channelID := st.StationID + "-" + ch.Code + "-" + strconv.Itoa(i+1)
				if _, err := tx.ExecContext(ctx,
					`INSERT INTO channels (channel_id, station_id, channel_code,
					        sample_rate_hz, azimuth_deg, dip_deg, depth_m,
					        validity_start, validity_end)
					 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
					channelID, st.StationID, ch.Code, ch.RateHz, ch.AzimuthDeg,
					ch.DipDeg, ch.DepthM, ep.Start, nullStr(ep.End)); err != nil {
					return c, err
				}
				c.Channels++
			}
		}
	}
	return c, tx.Commit()
}

// EnsureSeeded loads the seed only when the inventory is empty.
func EnsureSeeded(ctx context.Context, db *sql.DB, path string) (bool, Counts, error) {
	var n int
	if err := db.QueryRowContext(ctx, `SELECT count(*) FROM stations`).Scan(&n); err != nil {
		return false, Counts{}, err
	}
	if n != 0 {
		return false, Counts{}, nil
	}
	c, err := FromFile(ctx, db, path)
	return err == nil, c, err
}
