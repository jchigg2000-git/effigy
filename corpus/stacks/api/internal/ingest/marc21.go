// Package ingest reads MARCMaker (.mrk) records into the catalog database. It is a
// minimal reader scoped to the shape our own seed generator emits — not a
// general-purpose MARC 21 implementation, and not to be cited as one. Simplifications:
// one system record per file; one declared branch per file, any further branch a
// holding names being created on demand; a local profile for =583 and =876 in which
// =876 opens a loan and =583 supplies its dates under a $b == "D8" guard; indicators
// parsed but consulted only by =110; no character handling beyond the {dollar} escape.
package ingest

import (
	"context"
	"database/sql"
	"os"
	"strings"
)

type Counts struct {
	Systems      int `json:"systems"`
	Branches     int `json:"branches"`
	Holdings     int `json:"holdings"`
	Loans        int `json:"loans"`
	Borrowers    int `json:"borrowers"`
	Reservations int `json:"reservations"`
}

type subfield struct {
	Code  byte
	Value string
}

// seatBorrower registers a borrower id if it is new, tallying into the shared count.
func seatBorrower(ctx context.Context, tx *sql.Tx, borrowerID, branchID string, c *Counts) error {
	if borrowerID == "" {
		return nil
	}
	res, err := tx.ExecContext(ctx,
		`INSERT OR IGNORE INTO borrowers (borrower_id, home_branch_id) VALUES (?, ?)`,
		borrowerID, nullStr(branchID))
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n > 0 {
		c.Borrowers++
	}
	return nil
}

// parsedLoan doubles as the accumulator for a queued request: a reservation is a
// loan that has not started, so the same fields carry it.
type parsedLoan struct {
	ItemID, Type, Level, PolicyCode, BorrowerID string
	PickupBranch, EffectiveStart, EffectiveEnd  string
}

type parsedHolding struct {
	HoldingID, Author, Title, Statement, Published, Imprint  string
	Language, MaterialCode, CircStatus, CollectionCode, ISBN string
	DeskPhone, BranchID, CallNumber, Room, Wing, Bin         string
	Loans, Reservations                                      []parsedLoan
}

type parsedFile struct {
	SystemID, SystemName, BranchID, BranchName string
	RegistrySymbol, CollectionControlNumber    string
	Holdings                                   []parsedHolding
}

func sub(sfs []subfield, code byte) string {
	for _, sf := range sfs {
		if sf.Code == code {
			return strings.TrimSpace(sf.Value)
		}
	}
	return ""
}

// isoDate turns YYYYMMDD into YYYY-MM-DD and passes anything else back untouched.
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

// Parse walks the file a line at a time. The record and the loan under construction are
// held in this scope and mutated from inside the tag switch; the two flush closures take
// no arguments and read those variables directly, so a case arm closes a record blind.
func Parse(data []byte) *parsedFile {
	pf := &parsedFile{}
	var cur *parsedHolding
	var curLoan *parsedLoan
	flushLoan := func() {
		if cur != nil && curLoan != nil {
			cur.Loans = append(cur.Loans, *curLoan)
			curLoan = nil
		}
	}
	flushRecord := func() {
		flushLoan()
		if cur != nil {
			pf.Holdings = append(pf.Holdings, *cur)
			cur = nil
		}
	}
	for _, raw := range strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n") {
		line := strings.TrimRight(raw, " \t")
		if strings.TrimSpace(line) == "" {
			flushRecord()
			continue
		}
		if !strings.HasPrefix(line, "=") || len(line) < 6 {
			continue
		}
		tag := line[1:4]
		body := line[6:]
		if tag == "LDR" {
			flushRecord()
			cur = &parsedHolding{}
			if len(body) > 6 {
				cur.MaterialCode = string(body[5]) + string(body[6])
			}
			continue
		}
		if cur == nil {
			cur = &parsedHolding{}
		}
		var ind1 byte
		var sfs []subfield
		if tag >= "010" && len(body) >= 2 {
			ind1 = body[0]
			for _, chunk := range strings.Split(body[2:], "$") {
				if chunk != "" {
					sfs = append(sfs, subfield{chunk[0], strings.ReplaceAll(chunk[1:], "{dollar}", "$")})
				}
			}
		}
		switch tag {
		case "001":
			cur.HoldingID = strings.TrimSpace(body)
		case "010":
			if pf.CollectionControlNumber == "" {
				pf.CollectionControlNumber = sub(sfs, 'a')
			}
		case "020":
			cur.ISBN = sub(sfs, 'a')
		case "035":
			if pf.RegistrySymbol == "" {
				pf.RegistrySymbol = sub(sfs, 'a')
			}
		case "100":
			if len(sfs) > 0 {
				cur.Author = strings.TrimSuffix(sub(sfs, 'a'), ",")
			}
		case "245":
			if len(sfs) > 0 {
				cur.Title = strings.TrimSuffix(strings.TrimSpace(sfs[0].Value), " /")
			}
			if len(sfs) > 1 {
				cur.Statement = sfs[1].Value
			}
		case "260", "264":
			cur.Published = isoDate(strings.Trim(sub(sfs, 'c'), "."))
			cur.Imprint = strings.TrimSuffix(sub(sfs, 'b'), ",")
		case "270":
			if len(sfs) > 1 {
				cur.DeskPhone = strings.Map(func(r rune) rune {
					if r >= '0' && r <= '9' {
						return r
					}
					return -1
				}, sfs[1].Value)
			}
		case "590":
			cur.CircStatus = sub(sfs, 'a')
		case "650":
			cur.CollectionCode = strings.TrimSuffix(sub(sfs, 'a'), ".")
		case "852":
			for _, sf := range sfs {
				switch sf.Code {
				case 'a':
					cur.BranchID = strings.TrimSpace(sf.Value)
					if pf.BranchID == "" {
						pf.BranchID = cur.BranchID
					}
				case 'b':
					cur.Room = sf.Value
				case 'c':
					cur.Wing = sf.Value
				case 'h':
					cur.CallNumber = sf.Value
				case 'i':
					cur.CallNumber = strings.TrimSpace(cur.CallNumber + " " + sf.Value)
				case 'j':
					cur.Bin = sf.Value
				}
			}
		case "876":
			flushLoan()
			curLoan = &parsedLoan{ItemID: sub(sfs, 'a'), Type: sub(sfs, 'h'), Level: sub(sfs, 'j'),
				PolicyCode: sub(sfs, 'x'), BorrowerID: sub(sfs, '3'), PickupBranch: cur.BranchID}
		case "583":
			if curLoan != nil && len(sfs) >= 3 && sub(sfs, 'b') == "D8" {
				switch sub(sfs, 'a') {
				case "LOANSTART":
					curLoan.EffectiveStart = isoDate(sub(sfs, 'c'))
				case "LOANEND":
					curLoan.EffectiveEnd = isoDate(sub(sfs, 'c'))
				}
			}
			if sub(sfs, 'a') == "HOLDPLACED" {
				cur.Reservations = append(cur.Reservations, parsedLoan{Type: "QUEUED",
					BorrowerID: sub(sfs, '3'), PickupBranch: cur.BranchID,
					EffectiveStart: isoDate(sub(sfs, 'c'))})
			}
		case "110":
			if ind1 == '2' || ind1 == '\\' {
				switch sub(sfs, '4') {
				case "sys":
					pf.SystemID = sub(sfs, '0')
					pf.SystemName = sub(sfs, 'a')
				case "brn":
					pf.BranchID = sub(sfs, '0')
					pf.BranchName = sub(sfs, 'a')
				}
			}
		}
		// The policy-code path: the local profile lets it arrive on either line.
		if curLoan != nil && curLoan.PolicyCode == "" {
			if v := sub(sfs, 'x'); v != "" {
				curLoan.PolicyCode = v
			}
		}
	}
	flushRecord()
	return pf
}

// FromFile reloads the whole catalog from one seed file inside a transaction.
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
	for _, t := range []string{"reservations", "loans", "borrowers", "holdings", "branches", "systems"} {
		if _, err := tx.ExecContext(ctx, "DELETE FROM "+t); err != nil {
			return c, err
		}
	}
	if pf.SystemID != "" {
		if _, err := tx.ExecContext(ctx, `INSERT INTO systems (system_id, name) VALUES (?, ?)`,
			pf.SystemID, pf.SystemName); err != nil {
			return c, err
		}
		c.Systems++
	}
	if pf.BranchID != "" {
		if _, err := tx.ExecContext(ctx,
			`INSERT OR REPLACE INTO branches (branch_id, name, registry_symbol, system_id)
			 VALUES (?, ?, ?, ?)`, pf.BranchID, pf.BranchName, nullStr(pf.RegistrySymbol),
			nullStr(pf.SystemID)); err != nil {
			return c, err
		}
		c.Branches++
	}
	for _, h := range pf.Holdings {
		if h.HoldingID == "" || h.Title == "" {
			continue
		}
		if h.BranchID != "" && h.BranchID != pf.BranchID {
			label := strings.TrimPrefix(h.BranchID, "BR-")
			res, err := tx.ExecContext(ctx,
				`INSERT OR IGNORE INTO branches (branch_id, name, system_id) VALUES (?, ?, ?)`,
				h.BranchID, strings.ToUpper(label[:1])+strings.ToLower(label[1:])+" Branch",
				nullStr(pf.SystemID))
			if err != nil {
				return c, err
			}
			if n, _ := res.RowsAffected(); n > 0 {
				c.Branches++
			}
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO holdings (holding_id, branch_id, author, title, published, language,
			        material_code, circ_status, collection_code, isbn, desk_phone,
			        call_number, room, wing, bin)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			h.HoldingID, h.BranchID, strings.ToUpper(h.Author), strings.ToUpper(h.Title), h.Published,
			nullStr(h.Language), nullStr(h.MaterialCode), nullStr(h.CircStatus), nullStr(h.CollectionCode),
			nullStr(h.ISBN), nullStr(h.DeskPhone), nullStr(h.CallNumber), nullStr(h.Room),
			nullStr(h.Wing), nullStr(h.Bin)); err != nil {
			return c, err
		}
		c.Holdings++
		for _, l := range h.Loans {
			if l.Type == "" || l.EffectiveStart == "" {
				continue
			}
			if err := seatBorrower(ctx, tx, l.BorrowerID, h.BranchID, &c); err != nil {
				return c, err
			}
			if _, err := tx.ExecContext(ctx,
				`INSERT INTO loans (holding_id, borrower_id, loan_type, loan_level, policy_code,
				        pickup_branch, effective_start, effective_end)
				 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
				h.HoldingID, nullStr(l.BorrowerID), l.Type, nullStr(l.Level), nullStr(l.PolicyCode),
				nullStr(l.PickupBranch), l.EffectiveStart, nullStr(l.EffectiveEnd)); err != nil {
				return c, err
			}
			c.Loans++
		}
		for i, rq := range h.Reservations {
			if rq.BorrowerID == "" {
				continue
			}
			if err := seatBorrower(ctx, tx, rq.BorrowerID, h.BranchID, &c); err != nil {
				return c, err
			}
			if _, err := tx.ExecContext(ctx,
				`INSERT INTO reservations (holding_id, borrower_id, pickup_branch, placed_on,
				        queue_position, status) VALUES (?, ?, ?, ?, ?, ?)`,
				h.HoldingID, rq.BorrowerID, nullStr(rq.PickupBranch), rq.EffectiveStart,
				i+1, rq.Type); err != nil {
				return c, err
			}
			c.Reservations++
		}
	}
	return c, tx.Commit()
}

// EnsureSeeded loads the seed only when the catalog is empty.
func EnsureSeeded(ctx context.Context, db *sql.DB, path string) (bool, Counts, error) {
	var n int
	if err := db.QueryRowContext(ctx, `SELECT count(*) FROM holdings`).Scan(&n); err != nil {
		return false, Counts{}, err
	}
	if n != 0 {
		return false, Counts{}, nil
	}
	c, err := FromFile(ctx, db, path)
	return err == nil, c, err
}
