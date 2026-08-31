// Package ingest reads qsolog's local log-interchange profile into the
// logbook database. A record is a run of <tag:len>value fields terminated by
// a bare <fin> tag; there is no header block and no file-level version
// marker. This is a format of our own design — the tag vocabulary, the
// terminator, and the station-declaration convention below are not part of
// any published interchange standard, and nothing here should be cited as
// one.
//
// Two field groups share one record shape. A profile pair — sgrid and scls —
// declares or refreshes the operating station named by op; it may appear on
// any record, not only the first one for that station, and a later value
// replaces an earlier one. A contact is anything carrying wk: op worked wk on
// bnd/mode at qdate/qtime, and every field after that is optional detail.
package ingest

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"strings"
)

type Counts struct {
	Stations      int `json:"stations"`
	Contacts      int `json:"contacts"`
	Confirmations int `json:"confirmations"`
}

type parsedRecord struct {
	Op, SGrid, SCls             string
	Wk, Bnd, Mode, QDate, QTime string
	Txr, Rxr, WGrid, Ent, Pwr   string
}

// isoDate turns YYYYMMDD into YYYY-MM-DD and passes anything else back
// untouched.
func isoDate(d8 string) string {
	if len(d8) != 8 {
		return d8
	}
	return d8[0:4] + "-" + d8[4:6] + "-" + d8[6:8]
}

func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// nextField reads one <tag:len>value pair or the bare <fin> terminator
// starting at pos. It returns the tag, the value, the position just past what
// it consumed, and whether this was the terminator. A malformed tag —
// missing the closing '>', or a length that will not parse — is skipped by
// advancing past the '>', which lets the parser recover from a corrupt field
// instead of abandoning the rest of the record.
func nextField(line string, pos int) (tag, value string, next int, isTerm bool) {
	if pos >= len(line) || line[pos] != '<' {
		return "", "", pos + 1, false
	}
	rel := strings.IndexByte(line[pos:], '>')
	if rel < 0 {
		return "", "", len(line), false
	}
	head := line[pos+1 : pos+rel]
	closeAt := pos + rel + 1
	if head == "fin" {
		return "", "", closeAt, true
	}
	parts := strings.SplitN(head, ":", 2)
	if len(parts) != 2 {
		return "", "", closeAt, false
	}
	var n int
	if _, err := fmt.Sscanf(parts[1], "%d", &n); err != nil || n < 0 {
		return "", "", closeAt, false
	}
	if closeAt+n > len(line) {
		n = len(line) - closeAt
	}
	return parts[0], line[closeAt : closeAt+n], closeAt + n, false
}

// parseRecord walks one run of fields until nextField reports the terminator
// or the line runs out, whichever comes first. A record with no terminator at
// all is still returned: FromFile only requires wk, bnd, mode, qdate and
// qtime to be non-empty before it will insert a contact, so a truncated
// profile-only line is harmless.
func parseRecord(line string) parsedRecord {
	var pr parsedRecord
	pos := 0
	for pos < len(line) {
		tag, value, next, term := nextField(line, pos)
		pos = next
		if term {
			break
		}
		switch tag {
		case "op":
			pr.Op = value
		case "sgrid":
			pr.SGrid = value
		case "scls":
			pr.SCls = value
		case "wk":
			pr.Wk = value
		case "bnd":
			pr.Bnd = value
		case "mode":
			pr.Mode = value
		case "qdate":
			pr.QDate = value
		case "qtime":
			pr.QTime = value
		case "txr":
			pr.Txr = value
		case "rxr":
			pr.Rxr = value
		case "wgrid":
			pr.WGrid = value
		case "ent":
			pr.Ent = value
		case "pwr":
			pr.Pwr = value
		}
	}
	return pr
}

// Parse splits the file on newlines — one record per line, blank lines
// ignored — and hands each surviving line to parseRecord.
func Parse(data []byte) []parsedRecord {
	var out []parsedRecord
	for _, raw := range strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" {
			continue
		}
		out = append(out, parseRecord(line))
	}
	return out
}

// FromFile reloads the whole logbook from one seed file inside a transaction.
// Station rows are upserted as they are met: a bare op sighting ensures the
// row exists, and an op sighting carrying sgrid or scls refreshes its
// profile. Contact ids are minted here, sequentially, because the
// interchange format carries none of its own.
func FromFile(ctx context.Context, db *sql.DB, path string) (Counts, error) {
	var c Counts
	data, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	records := Parse(data)
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return c, err
	}
	defer tx.Rollback()
	for _, t := range []string{"confirmations", "contacts", "stations"} {
		if _, err := tx.ExecContext(ctx, "DELETE FROM "+t); err != nil {
			return c, err
		}
	}

	seenStations := map[string]bool{}
	seq := 0
	for _, r := range records {
		op := strings.TrimSpace(r.Op)
		if op == "" {
			continue
		}
		if r.SGrid != "" || r.SCls != "" {
			if _, err := tx.ExecContext(ctx,
				`INSERT OR REPLACE INTO stations (station_id, callsign, grid_square, operator_class)
				 VALUES (?, ?, ?, ?)`, op, op, nullStr(r.SGrid), nullStr(r.SCls)); err != nil {
				return c, err
			}
			if !seenStations[op] {
				c.Stations++
				seenStations[op] = true
			}
		} else if !seenStations[op] {
			if _, err := tx.ExecContext(ctx,
				`INSERT OR IGNORE INTO stations (station_id, callsign) VALUES (?, ?)`,
				op, op); err != nil {
				return c, err
			}
			seenStations[op] = true
			c.Stations++
		}
		if r.Wk == "" || r.Bnd == "" || r.Mode == "" || r.QDate == "" || r.QTime == "" {
			continue
		}
		seq++
		contactID := fmt.Sprintf("qso%07d", seq)
		if _, err := tx.ExecContext(ctx, `INSERT INTO contacts
		       (contact_id, station_id, worked_callsign, band, mode, contact_date, contact_time,
		        signal_sent, signal_received, grid_square, entity_code)
		       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			contactID, op, strings.ToUpper(r.Wk), r.Bnd, strings.ToUpper(r.Mode),
			isoDate(r.QDate), r.QTime, nullStr(r.Txr), nullStr(r.Rxr),
			nullStr(r.WGrid), nullStr(r.Ent)); err != nil {
			return c, err
		}
		c.Contacts++
	}
	return c, tx.Commit()
}

// EnsureSeeded loads the seed only when the logbook is empty.
func EnsureSeeded(ctx context.Context, db *sql.DB, path string) (bool, Counts, error) {
	var n int
	if err := db.QueryRowContext(ctx, `SELECT count(*) FROM contacts`).Scan(&n); err != nil {
		return false, Counts{}, err
	}
	if n != 0 {
		return false, Counts{}, nil
	}
	c, err := FromFile(ctx, db, path)
	return err == nil, c, err
}
