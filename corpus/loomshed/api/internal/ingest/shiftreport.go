// Package ingest reads Ashcombe Weaving Works' shift-report files into the
// production database. The format is a local profile invented for this
// mill's own MES exports — not a published interchange standard, and not to
// be cited as one. One block covers one loom's one shift; blocks are
// separated by a blank line. Each block is a run of "KEY: value" lines, plus
// zero or more "DEFECT:" lines. A line indented by exactly two spaces is a
// continuation of the immediately preceding DEFECT line's NOTE, appended
// with a single space — the mill's export tooling wraps a note that runs
// past 100 columns onto a second line rather than truncating it. A block
// looks like:
//
//	LOOM: LM-014
//	SHIFT: 2026-08-17/B
//	RUN: RUN-000456
//	LOT: LOT-0000123
//	ORDER: ORD-0004521
//	OPERATOR: OP-0042
//	OUTPUT_M: 412.5
//	PPM: 186
//	DOWNTIME_MIN: 35
//	DEFECT: WARP-BREAK SEV2 AT 118.0M NOTE=snag on beam three, cleared after
//	  tension adjustment and re-threaded before the shift resumed
//	DEFECT: WEFT-SNAG SEV1 AT 340.2M NOTE=dropped, no rework needed
package ingest

import (
	"context"
	"database/sql"
	"os"
	"regexp"
	"strconv"
	"strings"
)

type Counts struct {
	Looms        int `json:"looms"`
	YarnLots     int `json:"yarnLots"`
	Orders       int `json:"orders"`
	Runs         int `json:"runs"`
	ShiftOutputs int `json:"shiftOutputs"`
	Defects      int `json:"defects"`
}

type parsedDefect struct {
	Type     string
	Severity int
	MetersAt float64
	Note     string
}

// parsedBlock is one loom's one logged shift: the run it was worked against,
// the output and downtime for that shift alone, and whatever defects an
// operator flagged during it.
type parsedBlock struct {
	LoomID      string
	ShiftDate   string
	ShiftCode   string
	RunID       string
	LotID       string
	OrderID     string
	OperatorID  string
	OutputM     float64
	PicksPerMin int
	DowntimeMin int
	Defects     []parsedDefect
}

var defectLine = regexp.MustCompile(`^([A-Z][A-Z0-9-]*)\s+SEV([1-3])\s+AT\s+([0-9]+(?:\.[0-9]+)?)M(?:\s+NOTE=(.*))?$`)

// parseDefectLine reads the fixed-order DEFECT value: a type token, a
// SEV1..SEV3 severity, an AT position in metres, and an optional trailing
// NOTE= that runs to the end of the line (and may be extended by
// continuation lines afterward).
func parseDefectLine(v string) (parsedDefect, bool) {
	m := defectLine.FindStringSubmatch(strings.TrimSpace(v))
	if m == nil {
		return parsedDefect{}, false
	}
	sev, _ := strconv.Atoi(m[2])
	meters, _ := strconv.ParseFloat(m[3], 64)
	return parsedDefect{Type: m[1], Severity: sev, MetersAt: meters, Note: strings.TrimSpace(m[4])}, true
}

// parseShift splits "2026-08-17/B" into its date and single-letter shift code.
func parseShift(v string) (string, string) {
	parts := strings.SplitN(strings.TrimSpace(v), "/", 2)
	if len(parts) != 2 {
		return strings.TrimSpace(v), ""
	}
	return parts[0], parts[1]
}

// Parse walks the file a line at a time, accumulating one block until a
// blank line flushes it. The block under construction is held in this
// scope; a continuation line closes over it directly rather than being
// threaded through as an argument.
func Parse(data []byte) []parsedBlock {
	var out []parsedBlock
	var cur *parsedBlock
	flush := func() {
		if cur != nil && cur.LoomID != "" {
			out = append(out, *cur)
		}
		cur = nil
	}
	for _, raw := range strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n") {
		if strings.TrimSpace(raw) == "" {
			flush()
			continue
		}
		if strings.HasPrefix(raw, "  ") {
			if cur != nil && len(cur.Defects) > 0 {
				last := &cur.Defects[len(cur.Defects)-1]
				last.Note = strings.TrimSpace(last.Note + " " + strings.TrimSpace(raw))
			}
			continue
		}
		idx := strings.Index(raw, ":")
		if idx < 0 {
			continue
		}
		key := strings.TrimSpace(raw[:idx])
		val := strings.TrimSpace(raw[idx+1:])
		if key == "LOOM" {
			flush()
			cur = &parsedBlock{}
		}
		if cur == nil {
			continue
		}
		switch key {
		case "LOOM":
			cur.LoomID = val
		case "SHIFT":
			cur.ShiftDate, cur.ShiftCode = parseShift(val)
		case "RUN":
			cur.RunID = val
		case "LOT":
			cur.LotID = val
		case "ORDER":
			cur.OrderID = val
		case "OPERATOR":
			cur.OperatorID = val
		case "OUTPUT_M":
			cur.OutputM, _ = strconv.ParseFloat(val, 64)
		case "PPM":
			cur.PicksPerMin, _ = strconv.Atoi(val)
		case "DOWNTIME_MIN":
			cur.DowntimeMin, _ = strconv.Atoi(val)
		case "DEFECT":
			if d, ok := parseDefectLine(val); ok {
				cur.Defects = append(cur.Defects, d)
			}
		}
	}
	flush()
	return out
}

func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// titleFromID derives a placeholder label for an entity the format only ever
// references by id, e.g. "LM-014" becomes "Loom LM-014". It is not meant to
// be a real name, only something for a listing to show before anyone edits
// the record by hand.
func titleFromID(kind, id string) string {
	if id == "" {
		return id
	}
	return kind + " " + id
}

// FromFile reloads the whole production database from one shift-report file
// inside a transaction. Looms, yarn lots, orders and runs are all created on
// demand from the ids a block references — the format never carries a
// separate entity-registration section, only shift activity — so the first
// block to mention an id also supplies its placeholder label.
func FromFile(ctx context.Context, db *sql.DB, path string) (Counts, error) {
	var c Counts
	data, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	blocks := Parse(data)
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return c, err
	}
	defer tx.Rollback()
	for _, t := range []string{"defects", "shift_outputs", "runs", "orders", "yarn_lots", "looms"} {
		if _, err := tx.ExecContext(ctx, "DELETE FROM "+t); err != nil {
			return c, err
		}
	}
	runStarted := map[string]bool{}
	for _, b := range blocks {
		if b.LoomID == "" || b.RunID == "" {
			continue
		}
		res, err := tx.ExecContext(ctx,
			`INSERT OR IGNORE INTO looms (loom_id, name, loom_type) VALUES (?, ?, ?)`,
			b.LoomID, titleFromID("Loom", b.LoomID), "rapier")
		if err != nil {
			return c, err
		}
		if n, _ := res.RowsAffected(); n > 0 {
			c.Looms++
		}
		res, err = tx.ExecContext(ctx,
			`INSERT OR IGNORE INTO yarn_lots (lot_id, fiber_blend) VALUES (?, ?)`,
			b.LotID, titleFromID("Lot", b.LotID))
		if err != nil {
			return c, err
		}
		if n, _ := res.RowsAffected(); n > 0 {
			c.YarnLots++
		}
		res, err = tx.ExecContext(ctx,
			`INSERT OR IGNORE INTO orders (order_id, fabric_spec) VALUES (?, ?)`,
			b.OrderID, titleFromID("Order", b.OrderID))
		if err != nil {
			return c, err
		}
		if n, _ := res.RowsAffected(); n > 0 {
			c.Orders++
		}
		if !runStarted[b.RunID] {
			runStarted[b.RunID] = true
			res, err = tx.ExecContext(ctx,
				`INSERT OR IGNORE INTO runs (run_id, loom_id, lot_id, order_id, started_on, status)
				 VALUES (?, ?, ?, ?, ?, ?)`,
				b.RunID, b.LoomID, b.LotID, b.OrderID, b.ShiftDate, "running")
			if err != nil {
				return c, err
			}
			if n, _ := res.RowsAffected(); n > 0 {
				c.Runs++
			}
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO shift_outputs (run_id, shift_date, shift_code, operator_id,
			        output_m, picks_per_minute, downtime_min)
			 VALUES (?, ?, ?, ?, ?, ?, ?)`,
			b.RunID, b.ShiftDate, b.ShiftCode, nullStr(b.OperatorID),
			b.OutputM, b.PicksPerMin, b.DowntimeMin); err != nil {
			return c, err
		}
		c.ShiftOutputs++
		for _, d := range b.Defects {
			if _, err := tx.ExecContext(ctx,
				`INSERT INTO defects (run_id, shift_date, shift_code, defect_type,
				        severity, meters_at, note, status)
				 VALUES (?, ?, ?, ?, ?, ?, ?, 'open')`,
				b.RunID, b.ShiftDate, b.ShiftCode, d.Type, d.Severity, d.MetersAt, nullStr(d.Note)); err != nil {
				return c, err
			}
			c.Defects++
		}
	}
	return c, tx.Commit()
}

// EnsureSeeded loads the seed only when the production database is empty.
func EnsureSeeded(ctx context.Context, db *sql.DB, path string) (bool, Counts, error) {
	var n int
	if err := db.QueryRowContext(ctx, `SELECT count(*) FROM runs`).Scan(&n); err != nil {
		return false, Counts{}, err
	}
	if n != 0 {
		return false, Counts{}, nil
	}
	c, err := FromFile(ctx, db, path)
	return err == nil, c, err
}
