// Package ingest reads the MRIF (Meter Read Import Format) fixed-width feed
// into the metering database. MRIF is a local profile invented for this
// corpus item — it names no real AMR/AMI vendor and follows no published
// exchange standard. Layout below; columns are 0-indexed for Go slicing.
//
//	Header (one line, type 'H'):
//	  [0:1]   record type, always "H"
//	  [1:9]   file date, YYYYMMDD
//	  [9:15]  route code, e.g. "RT0007"
//	  [15:23] billing cycle code, e.g. "20260701"
//	  [23:40] reserved, space-filled
//
//	Detail (one line per read, type 'D'):
//	  [0:1]   record type, always "D"
//	  [1:11]  service point id, e.g. "SP-0000001"
//	  [11:21] meter id, e.g. "MTR-000001"
//	  [21:29] read date, YYYYMMDD
//	  [29:39] read value, zero-padded integer units
//	  [39:40] read type code: S scheduled, R re-read, E estimated
//	  [40:41] tolerance flag: Y or N
//	  [41:60] reserved, space-filled
//
//	Trailer (one line, type 'T'):
//	  [0:1]  record type, always "T"
//	  [1:9]  detail record count, zero-padded
//	  [9:20] reserved, space-filled
//
// Exactly one header opens the file and exactly one trailer closes it; the
// trailer's declared count is checked against the detail lines actually
// parsed, and a mismatch is a parse error rather than a warning a caller
// could shrug off.
package ingest

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Counts struct {
	ServicePoints int `json:"servicePoints"`
	Meters        int `json:"meters"`
	Reads         int `json:"reads"`
	BillingCycles int `json:"billingCycles"`
}

type parsedRead struct {
	ServicePointID, MeterID, ReadDate string
	ReadValue                         int
	ReadType                          string
	ToleranceFlag                     bool
}

type parsedFile struct {
	FileDate, RouteCode, CycleCode string
	Reads                          []parsedRead
}

var readTypeNames = map[byte]string{'S': "SCHEDULED", 'R': "RE-READ", 'E': "ESTIMATED"}

func field(line string, start, end int) string {
	if end > len(line) {
		end = len(line)
	}
	if start >= end {
		return ""
	}
	return strings.TrimSpace(line[start:end])
}

// Parse walks the file a line at a time. Blank lines are skipped, which lets
// a trailing newline at the end of the file pass without tripping the
// header/trailer ordering checks below.
func Parse(data []byte) (*parsedFile, error) {
	pf := &parsedFile{}
	sawHeader := false
	sawTrailer := false
	declaredCount := 0

	lines := strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n")
	for _, raw := range lines {
		if strings.TrimSpace(raw) == "" {
			continue
		}
		switch raw[0] {
		case 'H':
			if sawHeader {
				return nil, fmt.Errorf("mrif: duplicate header line")
			}
			sawHeader = true
			pf.FileDate = field(raw, 1, 9)
			pf.RouteCode = field(raw, 9, 15)
			pf.CycleCode = field(raw, 15, 23)
		case 'D':
			if !sawHeader {
				return nil, fmt.Errorf("mrif: detail line before header")
			}
			if sawTrailer {
				return nil, fmt.Errorf("mrif: detail line after trailer")
			}
			value, err := strconv.Atoi(field(raw, 29, 39))
			if err != nil {
				return nil, fmt.Errorf("mrif: bad read value: %w", err)
			}
			var typeCode byte
			if tc := field(raw, 39, 40); tc != "" {
				typeCode = tc[0]
			}
			readType, ok := readTypeNames[typeCode]
			if !ok {
				return nil, fmt.Errorf("mrif: unknown read type code %q", string(typeCode))
			}
			pf.Reads = append(pf.Reads, parsedRead{
				ServicePointID: field(raw, 1, 11),
				MeterID:        field(raw, 11, 21),
				ReadDate:       field(raw, 21, 29),
				ReadValue:      value,
				ReadType:       readType,
				ToleranceFlag:  field(raw, 40, 41) == "Y",
			})
		case 'T':
			if sawTrailer {
				return nil, fmt.Errorf("mrif: duplicate trailer line")
			}
			sawTrailer = true
			n, err := strconv.Atoi(field(raw, 1, 9))
			if err != nil {
				return nil, fmt.Errorf("mrif: bad trailer count: %w", err)
			}
			declaredCount = n
		default:
			return nil, fmt.Errorf("mrif: unrecognised record type %q", string(raw[0]))
		}
	}
	if !sawHeader {
		return nil, fmt.Errorf("mrif: missing header line")
	}
	if !sawTrailer {
		return nil, fmt.Errorf("mrif: missing trailer line")
	}
	if declaredCount != len(pf.Reads) {
		return nil, fmt.Errorf("mrif: trailer declared %d detail records, parsed %d",
			declaredCount, len(pf.Reads))
	}
	return pf, nil
}

func nullStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// FromFile reloads the metering database from one MRIF feed inside a
// transaction. Service points and meters are upserted since the same ones
// recur across every cycle's feed; reads are always inserted fresh because a
// read id is unique to its file and line.
func FromFile(ctx context.Context, db *sql.DB, path string) (Counts, error) {
	var c Counts
	data, err := os.ReadFile(path)
	if err != nil {
		return c, err
	}
	pf, err := Parse(data)
	if err != nil {
		return c, err
	}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return c, err
	}
	defer tx.Rollback()

	if pf.CycleCode != "" {
		if _, err := tx.ExecContext(ctx,
			`INSERT OR IGNORE INTO billing_cycles (cycle_code, status, route_code)
			 VALUES (?, 'OPEN', ?)`, pf.CycleCode, pf.RouteCode); err != nil {
			return c, err
		}
		c.BillingCycles++
	}

	for i, rd := range pf.Reads {
		if rd.ServicePointID == "" || rd.MeterID == "" {
			continue
		}
		res, err := tx.ExecContext(ctx,
			`INSERT OR IGNORE INTO service_points (service_point_id, route_code) VALUES (?, ?)`,
			rd.ServicePointID, pf.RouteCode)
		if err != nil {
			return c, err
		}
		if n, _ := res.RowsAffected(); n > 0 {
			c.ServicePoints++
		}
		res, err = tx.ExecContext(ctx,
			`INSERT OR IGNORE INTO meters (meter_id, serial_number, service_point_id)
			 VALUES (?, ?, ?)`, rd.MeterID, fmt.Sprintf("SN%08d", i+1), rd.ServicePointID)
		if err != nil {
			return c, err
		}
		if n, _ := res.RowsAffected(); n > 0 {
			c.Meters++
		}
		readID := fmt.Sprintf("RD-%s-%04d", pf.CycleCode, i+1)
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO reads (read_id, meter_id, service_point_id, route_code, cycle_code,
			        read_type, read_value, read_date, tolerance_flag)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			readID, rd.MeterID, rd.ServicePointID, pf.RouteCode, nullStr(pf.CycleCode),
			rd.ReadType, rd.ReadValue, rd.ReadDate, rd.ToleranceFlag); err != nil {
			return c, err
		}
		c.Reads++
	}
	return c, tx.Commit()
}

// EnsureSeeded loads the seed only when the metering database is empty.
func EnsureSeeded(ctx context.Context, db *sql.DB, path string) (bool, Counts, error) {
	var n int
	if err := db.QueryRowContext(ctx, `SELECT count(*) FROM reads`).Scan(&n); err != nil {
		return false, Counts{}, err
	}
	if n != 0 {
		return false, Counts{}, nil
	}
	c, err := FromFile(ctx, db, path)
	return err == nil, c, err
}
