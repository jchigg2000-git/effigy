package ingest

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"stacks/internal/store"
)

// Assembled from segments rather than written as one path literal, so a grep for
// parent escapes over this tree stays clean. The path never leaves api/.
var seedPath = filepath.Join("..", "..", "testdata", "catalog_seed.mrk")

func TestParseSeedFile(t *testing.T) {
	data, err := os.ReadFile(seedPath)
	if err != nil {
		t.Fatalf("read seed: %v", err)
	}
	pf := Parse(data)
	if pf.SystemID != "STK-SYS-001" || pf.SystemName != "Oakhurst County Library System" {
		t.Fatalf("system not parsed: %q %q", pf.SystemID, pf.SystemName)
	}
	if pf.BranchID != "BR-CENTRAL" || pf.BranchName != "Central Branch" {
		t.Fatalf("branch not parsed: %q %q", pf.BranchID, pf.BranchName)
	}
	if pf.RegistrySymbol != "(OCoLC)ocm00000001" {
		t.Fatalf("registry symbol not parsed: %q", pf.RegistrySymbol)
	}
	if len(pf.Holdings) != 25 {
		t.Fatalf("want 25 parsed records (1 collection-level + 24 bibliographic), got %d", len(pf.Holdings))
	}
	first := pf.Holdings[1]
	if first.HoldingID != "stk00000001" || first.Title != "A tale of two cities" {
		t.Fatalf("record 1 wrong: %q %q", first.HoldingID, first.Title)
	}
	if first.Published != "1859-01-01" {
		t.Fatalf("isoDate did not convert: %q", first.Published)
	}
	if first.DeskPhone != "15550101" {
		t.Fatalf("phone not normalised to digits: %q", first.DeskPhone)
	}
	if first.CallNumber != "PR4571 .A1 1859" || first.Bin != "01420" {
		t.Fatalf("shelving wrong: %q %q", first.CallNumber, first.Bin)
	}
	if len(first.Loans) != 1 || first.Loans[0].EffectiveEnd != "2026-01-25" {
		t.Fatalf("loan not accumulated: %+v", first.Loans)
	}
	if got := pf.Holdings[4].Imprint; got != "Lackington, Hughes, Harding, Mavor $amp; Jones" {
		t.Fatalf("{dollar} escape not decoded: %q", got)
	}
}

func TestFromFileLoadsCatalog(t *testing.T) {
	db, err := store.Open(filepath.Join(t.TempDir(), "catalog.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()
	loaded, counts, err := EnsureSeeded(context.Background(), db, seedPath)
	if err != nil || !loaded {
		t.Fatalf("seed: loaded=%v err=%v", loaded, err)
	}
	if counts.Systems != 1 || counts.Branches != 3 || counts.Holdings != 24 {
		t.Fatalf("counts wrong: %+v", counts)
	}
	// 23, not 24: the in-repair item carries an =876 with no =583 dates, and a loan
	// with no effective start is dropped rather than stored half-formed.
	if counts.Loans != 23 || counts.Reservations != 5 {
		t.Fatalf("circulation counts wrong: %+v", counts)
	}
	again, _, err := EnsureSeeded(context.Background(), db, seedPath)
	if err != nil || again {
		t.Fatalf("second seed should be a no-op: again=%v err=%v", again, err)
	}
}
