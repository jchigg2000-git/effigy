package interchange

import (
	"encoding/json"
	"regexp"
	"sort"
	"strings"
	"testing"

	"stacks/internal/model"
)

// exportOf marshals a record set and returns the JSON alongside every distinct
// coding system in it: the profile only ever names urn-shaped systems, so the
// deduplicated matches are the whole vocabulary of one export.
func exportOf(t *testing.T, set RecordSet) (string, []string) {
	t.Helper()
	raw, err := json.Marshal(set)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	seen := map[string]bool{}
	urns := []string{}
	for _, m := range regexp.MustCompile(`urn:[a-z:-]+`).FindAllString(string(raw), -1) {
		if !seen[m] {
			seen[m] = true
			urns = append(urns, m)
		}
	}
	sort.Strings(urns)
	return string(raw), urns
}

func TestBuildRecordSetFromFullHolding(t *testing.T) {
	// The loan carries a level and a policy code, so both class ladders open. Neither
	// class seats a urn: system, so the vocabulary is still the five asserted below.
	h := model.Holding{
		HoldingID: "stk00000001", BranchID: "BR-CENTRAL",
		Author: "DICKENS, CHARLES", Title: "A TALE OF TWO CITIES",
		Published: "1859-01-01", Language: "EN", MaterialCode: "na",
		CircStatus: "ON-SHELF", CollectionCode: "Historical fiction",
		ISBN: "978-0-00-000001-9", DeskPhone: "15550101",
		Shelf: model.Shelf{CallNumber: "PR4571 .A1 1859", Room: "Main Reading Room",
			Wing: "NW", Bin: "01420"},
		Branch: &model.Branch{BranchID: "BR-CENTRAL", Name: "Central Branch",
			RegistrySymbol: "(OCoLC)ocm00000001", SystemID: "STK-SYS-001"},
		Loans: []model.Loan{{Type: "LOAN", Level: "STD", PolicyCode: "CIRC-21D",
			EffectiveStart: "2026-01-04", EffectiveEnd: "2026-01-25",
			BorrowerID: "BRW-0000001", PickupBranch: "BR-CENTRAL"}},
	}
	set := BuildRecordSet(h)
	if set.RecordType != "RecordSet" || set.Type != "collection" || len(set.Entry) != 3 {
		t.Fatalf("want a RecordSet of Record, Collection and one Availability: %+v", set)
	}
	rec, ok := set.Entry[0].Resource.(Record)
	if !ok || rec.RecordType != "Record" || rec.ID != "stk00000001" ||
		set.Entry[0].FullURL != "Record/stk00000001" {
		t.Fatalf("record entry: %T %+v", set.Entry[0].Resource, set.Entry[0])
	}
	// The holding id is seated first unconditionally; the ISBN is appended after it.
	if len(rec.Identifier) != 2 || rec.Identifier[0].System != "urn:stacks:holding-id" ||
		rec.Identifier[0].Value != "stk00000001" || rec.Identifier[1].System != "urn:isbn:" ||
		rec.Identifier[1].Value != "978-0-00-000001-9" {
		t.Fatalf("record identifiers: %+v", rec.Identifier)
	}
	if rec.Title[0].Text != "A TALE OF TWO CITIES" || rec.Creator != "DICKENS, CHARLES" ||
		rec.Language != "eng" || rec.Date != "1859-01-01" || rec.Format != "na" {
		t.Fatalf("record body: %+v", rec)
	}
	if len(rec.Contact) != 1 || rec.Contact[0].Value != "15550101" || len(rec.Location) != 1 ||
		rec.Location[0].Line[0] != "PR4571 .A1 1859" || rec.Location[0].Bin != "01420" {
		t.Fatalf("contact and location: %+v %+v", rec.Contact, rec.Location)
	}
	col, ok := set.Entry[1].Resource.(Collection)
	if !ok || col.RecordType != "Collection" || col.ID != "BR-CENTRAL" ||
		col.Name != "Central Branch" || set.Entry[1].FullURL != "Collection/BR-CENTRAL" {
		t.Fatalf("collection entry: %T %+v", set.Entry[1].Resource, set.Entry[1])
	}
	// The registry symbol and the system id seat one identifier each, in that order.
	if len(col.Identifier) != 2 || col.Identifier[0].System != "urn:oclc:" ||
		col.Identifier[0].Value != "(OCoLC)ocm00000001" ||
		col.Identifier[1].System != "urn:lccn:" || col.Identifier[1].Value != "STK-SYS-001" {
		t.Fatalf("collection identifiers: %+v", col.Identifier)
	}
	if col.PartOf == nil || col.PartOf.Ref != "System/STK-SYS-001" {
		t.Fatalf("partOf: %+v", col.PartOf)
	}

	av, ok := set.Entry[2].Resource.(Availability)
	if !ok || av.RecordType != "Availability" || av.Status != "active" ||
		av.Holder != "BR-CENTRAL" || av.Item.Ref != "Record/stk00000001" {
		t.Fatalf("availability entry: %T %+v", set.Entry[2].Resource, set.Entry[2])
	}
	// The policy code names the entry; the ordinal fallback is in the idOrIndex table.
	if av.ID != "CIRC-21D" || set.Entry[2].FullURL != "Availability/CIRC-21D" || len(av.Class) != 2 {
		t.Fatalf("availability naming: %q %q %+v", av.ID, set.Entry[2].FullURL, av.Class)
	}
	// Level first, then policy code, and neither coding carries a system.
	if av.Class[0].Value != "STD" || av.Class[0].Type.Coding[0].Code != "STD" ||
		av.Class[0].Type.Coding[0].System != "" || av.Class[1].Value != "CIRC-21D" ||
		av.Class[1].Type.Coding[0].Code != "CIRC-21D" ||
		av.Class[1].Type.Coding[0].System != "" {
		t.Fatalf("availability classes: %+v", av.Class)
	}
	if len(av.Kind.Coding) != 1 || av.Kind.Coding[0].System != "urn:stacks:branch-id" ||
		av.Kind.Coding[0].Code != "BR-CENTRAL" || av.Kind.Text != "LOAN" {
		t.Fatalf("kind coding: %+v", av.Kind)
	}
	if av.Period.Start != "2026-01-04" || av.Period.End != "2026-01-25" ||
		av.Custodian == nil || av.Custodian.Ref != "Collection/BR-CENTRAL" {
		t.Fatalf("period and custodian: %+v %+v", av.Period, av.Custodian)
	}

	blob, urns := exportOf(t, set)
	want := []string{"urn:isbn:", "urn:lccn:", "urn:oclc:", "urn:stacks:branch-id", "urn:stacks:holding-id"}
	if strings.Join(urns, " ") != strings.Join(want, " ") {
		t.Fatalf("coding systems %v, want exactly %v", urns, want)
	}
	// Borrower identity rides on the loan but is never read by the builder.
	if strings.Contains(blob, "BRW-") {
		t.Fatalf("borrower id reached the export: %s", blob)
	}
}

// A holding with nothing optional set collapses the omit-if-empty ladder all the
// way down: one entry, no location, no contact, and no branch or loan entries.
func TestBuildRecordSetFromSparseHolding(t *testing.T) {
	set := BuildRecordSet(model.Holding{
		HoldingID: "stk00000010", BranchID: "BR-EASTSIDE",
		Author: "SWIFT, JONATHAN", Title: "GULLIVER'S TRAVELS", Published: "1726-10-28",
	})
	if len(set.Entry) != 1 {
		t.Fatalf("no branch and no loans should leave one entry, got %d", len(set.Entry))
	}
	if rec := set.Entry[0].Resource.(Record); rec.Location != nil || rec.Contact != nil ||
		len(rec.Identifier) != 1 || rec.Identifier[0].System != "urn:stacks:holding-id" {
		t.Fatalf("sparse record: %+v", rec)
	}
	blob, _ := exportOf(t, set)
	want := `{"recordType":"RecordSet","type":"collection","entry":[` +
		`{"fullUrl":"Record/stk00000010","resource":{"recordType":"Record","id":"stk00000010",` +
		`"identifier":[{"system":"urn:stacks:holding-id","value":"stk00000010"}],` +
		`"title":[{"text":"GULLIVER'S TRAVELS"}],"creator":"SWIFT, JONATHAN",` +
		`"date":"1726-10-28"}}]}`
	if blob != want {
		t.Fatalf("sparse export\n got %s\nwant %s", blob, want)
	}
	// An unset language maps to the empty string, so the key drops out entirely.
	for _, key := range []string{"language", "format", "location", "contact", "partOf", "Availability"} {
		if strings.Contains(blob, key) {
			t.Fatalf("%q should have been omitted: %s", key, blob)
		}
	}
}

func TestLanguageAndOrdinalHelpers(t *testing.T) {
	langs := map[string]string{"EN": "eng", "en": "eng", "ES": "spa", "es": "spa",
		"FR": "fre", "fr": "fre", "UND": "und", "und": "und", "": "",
		"DE": "mul", "eng": "mul", "zz": "mul"}
	for in, want := range langs {
		if got := mapLanguage(in); got != want {
			t.Fatalf("mapLanguage(%q) = %q, want %q", in, got, want)
		}
	}
	ints := map[int]string{0: "0", 7: "7", 42: "42", 1859: "1859", -3: "-3", -1024: "-1024"}
	for in, want := range ints {
		if got := itoa(in); got != want {
			t.Fatalf("itoa(%d) = %q, want %q", in, got, want)
		}
	}
	// A policy code passes through; an entry without one is named by its ordinal.
	if idOrIndex("CIRC-21D", 0) != "CIRC-21D" || idOrIndex("ILL-14D", 3) != "ILL-14D" ||
		idOrIndex("", 0) != "loan-0" || idOrIndex("", 12) != "loan-12" {
		t.Fatalf("idOrIndex: %q %q", idOrIndex("CIRC-21D", 0), idOrIndex("", 12))
	}
}
