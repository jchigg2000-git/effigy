// Package ingest reads the tailwatch fleet-seed file: a line-oriented,
// block-structured local profile invented for this project. It is not any
// published airworthiness-directive interchange standard and must not be
// cited as one — it exists only to get fabricated fleet data into the
// database in a shape that looks like a real interchange file would.
//
// A block opens with a keyword line naming its kind and its id, carries one
// "KEY value" pair per line, and closes with a bare END line:
//
//	AIRFRAME N0TW-1004
//	TYPE HA-228
//	STATUS IN_SERVICE
//	END
//
// Tail numbers are fictions drawn from the N0 block: a real US registration
// never carries "0" as the digit right after the N, so nothing seeded here
// can collide with an assigned one. Part numbers, serials and directive ids
// are likewise sequential fictions under a domain prefix (PN-, SN-, and the
// invented regulator's own directive-id format), never a real identifier.
// APPLIES-* lines inside a DIRECTIVE block are applicability predicates and
// may repeat; every other key is expected once. Five block kinds exist:
// AIRFRAME, COMPONENT, LIFE-LIMIT, DIRECTIVE, COMPLIANCE. Lines outside any
// block, and blank lines, are ignored, which is what lets "#" comment lines
// sit between blocks with no special-casing.
package ingest

import (
	"context"
	"database/sql"
	"os"
	"strconv"
	"strings"
)

type Counts struct {
	Airframes          int `json:"airframes"`
	Components         int `json:"components"`
	LifeLimits         int `json:"lifeLimits"`
	Directives         int `json:"directives"`
	ApplicabilityRules int `json:"applicabilityRules"`
	ComplianceRecords  int `json:"complianceRecords"`
}

type parsedAirframe struct {
	TailNumber, TypeDesignation, OperatorCode string
	ManufacturedOn, Hours, Cycles, Status     string
}

type parsedComponent struct {
	ComponentID, TailNumber, PositionCode, ParentPositionCode string
	Category, Label, PartNumber, SerialNumber                 string
	InstalledOn, InstalledHours, InstalledCycles              string
}

type parsedLifeLimit struct {
	PartNumber, LimitHours, LimitCycles, LimitDays string
}

type applicabilityRule struct {
	Type, Value, SerialMin, SerialMax string
}

type parsedDirective struct {
	DirectiveID, Title, IssuedBy, IssuedOn, EffectiveOn   string
	Category, IntervalHours, IntervalCycles, IntervalDays string
	Rules                                                 []applicabilityRule
}

type parsedCompliance struct {
	DirectiveID, ComponentID, CompliedOn, Method, NextDueOn, Status string
}

type parsedFile struct {
	Airframes  []parsedAirframe
	Components []parsedComponent
	LifeLimits []parsedLifeLimit
	Directives []parsedDirective
	Compliance []parsedCompliance
}

// Parse walks the file a line at a time. Exactly one of the five accumulator
// pointers is non-nil while a block is open; kind says which. flush appends
// whichever accumulator is set and clears all five, so a stray END with
// nothing open is simply a no-op rather than an error.
// Parse walks the file a line at a time. Rather than a per-block-kind switch
// on every key (the shape a tag-per-line reader would use), each block, on open,
// publishes a map of its own field addresses; an ordinary "KEY value" line
// is then just a map lookup and a pointer write. DIRECTIVE's APPLIES-* lines
// are the one exception — they repeat, so no single *string slot can hold
// them, and they are matched before the field-map fallback.
func Parse(data []byte) *parsedFile {
	pf := &parsedFile{}
	var kind string
	var af *parsedAirframe
	var cmp *parsedComponent
	var lim *parsedLifeLimit
	var dir *parsedDirective
	var comp *parsedCompliance
	var fields map[string]*string

	flush := func() {
		switch kind {
		case "AIRFRAME":
			if af != nil {
				pf.Airframes = append(pf.Airframes, *af)
			}
		case "COMPONENT":
			if cmp != nil {
				pf.Components = append(pf.Components, *cmp)
			}
		case "LIFE-LIMIT":
			if lim != nil {
				pf.LifeLimits = append(pf.LifeLimits, *lim)
			}
		case "DIRECTIVE":
			if dir != nil {
				pf.Directives = append(pf.Directives, *dir)
			}
		case "COMPLIANCE":
			if comp != nil {
				pf.Compliance = append(pf.Compliance, *comp)
			}
		}
		kind, af, cmp, lim, dir, comp, fields = "", nil, nil, nil, nil, nil, nil
	}

	for _, raw := range strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if line == "END" {
			flush()
			continue
		}
		head, rest, _ := strings.Cut(line, " ")
		rest = strings.TrimSpace(rest)

		switch head {
		case "AIRFRAME":
			flush()
			af, kind = &parsedAirframe{TailNumber: rest}, "AIRFRAME"
			fields = map[string]*string{"TYPE": &af.TypeDesignation, "OPERATOR": &af.OperatorCode,
				"MANUFACTURED": &af.ManufacturedOn, "HOURS": &af.Hours, "CYCLES": &af.Cycles,
				"STATUS": &af.Status}
			continue
		case "COMPONENT":
			flush()
			cmp, kind = &parsedComponent{ComponentID: rest}, "COMPONENT"
			fields = map[string]*string{"TAIL": &cmp.TailNumber, "POSITION": &cmp.PositionCode,
				"PARENT": &cmp.ParentPositionCode, "CATEGORY": &cmp.Category, "LABEL": &cmp.Label,
				"PART": &cmp.PartNumber, "SERIAL": &cmp.SerialNumber, "INSTALLED": &cmp.InstalledOn,
				"INSTALLED-HOURS": &cmp.InstalledHours, "INSTALLED-CYCLES": &cmp.InstalledCycles}
			continue
		case "LIFE-LIMIT":
			flush()
			lim, kind = &parsedLifeLimit{PartNumber: rest}, "LIFE-LIMIT"
			fields = map[string]*string{"LIMIT-HOURS": &lim.LimitHours,
				"LIMIT-CYCLES": &lim.LimitCycles, "LIMIT-DAYS": &lim.LimitDays}
			continue
		case "DIRECTIVE":
			flush()
			dir, kind = &parsedDirective{DirectiveID: rest}, "DIRECTIVE"
			fields = map[string]*string{"TITLE": &dir.Title, "ISSUED-BY": &dir.IssuedBy,
				"ISSUED": &dir.IssuedOn, "EFFECTIVE": &dir.EffectiveOn, "CATEGORY": &dir.Category,
				"INTERVAL-HOURS": &dir.IntervalHours, "INTERVAL-CYCLES": &dir.IntervalCycles,
				"INTERVAL-DAYS": &dir.IntervalDays}
			continue
		case "COMPLIANCE":
			flush()
			ids := strings.Fields(rest)
			comp, kind = &parsedCompliance{}, "COMPLIANCE"
			if len(ids) > 0 {
				comp.DirectiveID = ids[0]
			}
			if len(ids) > 1 {
				comp.ComponentID = ids[1]
			}
			fields = map[string]*string{"DONE": &comp.CompliedOn, "METHOD": &comp.Method,
				"NEXT-DUE": &comp.NextDueOn, "STATUS": &comp.Status}
			continue
		}

		if kind == "DIRECTIVE" {
			switch head {
			case "APPLIES-TYPE":
				dir.Rules = append(dir.Rules, applicabilityRule{Type: "TYPE", Value: rest})
				continue
			case "APPLIES-POSITION":
				dir.Rules = append(dir.Rules, applicabilityRule{Type: "POSITION", Value: rest})
				continue
			case "APPLIES-PART":
				dir.Rules = append(dir.Rules, applicabilityRule{Type: "PART", Value: rest})
				continue
			case "APPLIES-SERIAL":
				lo, hi, _ := strings.Cut(rest, "..")
				dir.Rules = append(dir.Rules, applicabilityRule{Type: "SERIAL_RANGE", SerialMin: lo, SerialMax: hi})
				continue
			}
		}
		if p, ok := fields[head]; ok {
			*p = rest
		}
	}
	flush()
	return pf
}

func nullFloat(s string) sql.NullFloat64 {
	v, err := strconv.ParseFloat(strings.TrimSpace(s), 64)
	if err != nil {
		return sql.NullFloat64{}
	}
	return sql.NullFloat64{Float64: v, Valid: true}
}

func nullInt(s string) sql.NullInt64 {
	v, err := strconv.ParseInt(strings.TrimSpace(s), 10, 64)
	if err != nil {
		return sql.NullInt64{}
	}
	return sql.NullInt64{Int64: v, Valid: true}
}

func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// FromFile reloads the whole fleet from one seed file inside a transaction.
// Insert order follows the reference shape rather than any declared foreign
// key: airframes before the components installed on them, directives before
// the applicability rules and compliance records that name them.
func FromFile(ctx context.Context, db *sql.DB, path string) (Counts, error) {
	var c Counts
	data, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	pf := Parse(data)
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return c, err
	}
	defer tx.Rollback()
	for _, t := range []string{"compliance_records", "directive_applicability", "directives",
		"life_limits", "components", "airframes"} {
		if _, err := tx.ExecContext(ctx, "DELETE FROM "+t); err != nil {
			return c, err
		}
	}
	for _, a := range pf.Airframes {
		if a.TailNumber == "" {
			continue
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO airframes (tail_number, type_designation, operator_code, manufactured_on,
			        total_hours, total_cycles, status)
			 VALUES (?, ?, ?, ?, ?, ?, ?)`,
			a.TailNumber, a.TypeDesignation, a.OperatorCode, nullStr(a.ManufacturedOn),
			nullFloat(a.Hours), nullInt(a.Cycles), a.Status); err != nil {
			return c, err
		}
		c.Airframes++
	}
	for _, cm := range pf.Components {
		if cm.ComponentID == "" || cm.TailNumber == "" {
			continue
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO components (component_id, tail_number, position_code, parent_position_code,
			        category, label, part_number, serial_number, installed_on, installed_hours,
			        installed_cycles)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			cm.ComponentID, cm.TailNumber, cm.PositionCode, nullStr(cm.ParentPositionCode),
			cm.Category, cm.Label, cm.PartNumber, cm.SerialNumber, cm.InstalledOn,
			nullFloat(cm.InstalledHours), nullInt(cm.InstalledCycles)); err != nil {
			return c, err
		}
		c.Components++
	}
	for _, l := range pf.LifeLimits {
		if l.PartNumber == "" {
			continue
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO life_limits (part_number, limit_hours, limit_cycles, limit_calendar_days)
			 VALUES (?, ?, ?, ?)`,
			l.PartNumber, nullFloat(l.LimitHours), nullInt(l.LimitCycles), nullInt(l.LimitDays)); err != nil {
			return c, err
		}
		c.LifeLimits++
	}
	for _, d := range pf.Directives {
		if d.DirectiveID == "" {
			continue
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO directives (directive_id, title, issued_by, issued_on, effective_on,
			        category, interval_hours, interval_cycles, interval_days)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			d.DirectiveID, d.Title, d.IssuedBy, d.IssuedOn, nullStr(d.EffectiveOn), d.Category,
			nullFloat(d.IntervalHours), nullInt(d.IntervalCycles), nullInt(d.IntervalDays)); err != nil {
			return c, err
		}
		c.Directives++
		for _, rule := range d.Rules {
			if _, err := tx.ExecContext(ctx,
				`INSERT INTO directive_applicability (directive_id, predicate_type, predicate_value,
				        serial_min, serial_max)
				 VALUES (?, ?, ?, ?, ?)`,
				d.DirectiveID, rule.Type, nullStr(rule.Value), nullStr(rule.SerialMin),
				nullStr(rule.SerialMax)); err != nil {
				return c, err
			}
			c.ApplicabilityRules++
		}
	}
	for _, r := range pf.Compliance {
		if r.DirectiveID == "" || r.ComponentID == "" || r.CompliedOn == "" {
			continue
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO compliance_records (directive_id, component_id, complied_on, method,
			        next_due_on, status)
			 VALUES (?, ?, ?, ?, ?, ?)`,
			r.DirectiveID, r.ComponentID, r.CompliedOn, r.Method, nullStr(r.NextDueOn),
			r.Status); err != nil {
			return c, err
		}
		c.ComplianceRecords++
	}
	return c, tx.Commit()
}

// EnsureSeeded loads the seed only when the fleet is empty.
func EnsureSeeded(ctx context.Context, db *sql.DB, path string) (bool, Counts, error) {
	var n int
	if err := db.QueryRowContext(ctx, `SELECT count(*) FROM components`).Scan(&n); err != nil {
		return false, Counts{}, err
	}
	if n != 0 {
		return false, Counts{}, nil
	}
	c, err := FromFile(ctx, db, path)
	return err == nil, c, err
}
