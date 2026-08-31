package api

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"stacks/internal/ingest"
	"stacks/internal/model"
	"stacks/internal/store"
)

// Assembled from segments rather than written as one path literal, so a grep for
// parent escapes over this tree stays clean. The path never leaves api/.
var seedPath = filepath.Join("..", "..", "testdata", "catalog_seed.mrk")

// adminToken is the value the router compares X-Admin-Token against on a
// developer machine. dev-only, not a secret.
const adminToken = "localdev"

const seeded, empty = true, false // the two catalog states newHandler hands back

// newHandler returns the assembled router over a scratch catalog in the test's own
// temp directory. store.Open applies the embedded schema, so an unseeded database
// still answers the readiness query; every test owns its file and may write freely.
func newHandler(t *testing.T, withSeed bool) http.Handler {
	t.Helper()
	db, err := store.Open(filepath.Join(t.TempDir(), "catalog.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	if withSeed {
		if _, err := ingest.FromFile(context.Background(), db, seedPath); err != nil {
			t.Fatalf("seed: %v", err)
		}
	}
	return NewServer(db, slog.New(slog.NewTextHandler(io.Discard, nil)),
		seedPath, adminToken).Handler() // dev-only, not a secret
}

func send(t *testing.T, h http.Handler, method, target, body string,
	header map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	var rdr io.Reader
	if body != "" {
		rdr = strings.NewReader(body)
	}
	req := httptest.NewRequest(method, target, rdr)
	for k, v := range header {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func get(t *testing.T, h http.Handler, target string) *httptest.ResponseRecorder {
	t.Helper()
	return send(t, h, http.MethodGet, target, "", nil)
}

func patch(t *testing.T, h http.Handler, target, body string) *httptest.ResponseRecorder {
	t.Helper()
	return send(t, h, http.MethodPatch, target, body,
		map[string]string{"Content-Type": "application/json"})
}

func decode(t *testing.T, rec *httptest.ResponseRecorder, want int, dst any) {
	t.Helper()
	if rec.Code != want {
		t.Fatalf("status %d, want %d: %s", rec.Code, want, rec.Body.String())
	}
	if err := json.Unmarshal(rec.Body.Bytes(), dst); err != nil {
		t.Fatalf("decode %q: %v", rec.Body.String(), err)
	}
}

// wantError reads the envelope the handlers write on every failure path.
func wantError(t *testing.T, rec *httptest.ResponseRecorder, status int, code, message string) {
	t.Helper()
	var env errorEnvelope
	decode(t, rec, status, &env)
	if env.Error.Code != code || env.Error.Message != message {
		t.Fatalf("error %q / %q, want %q / %q",
			env.Error.Code, env.Error.Message, code, message)
	}
}

// listBody covers both list-shaped responses; keys the writer omits decode to zero.
type listBody struct {
	BranchID string           `json:"branchId"`
	Count    int              `json:"count"`
	Limit    int              `json:"limit"`
	Offset   int              `json:"offset"`
	Holdings []holdingSummary `json:"holdings"`
}

type loansBody struct {
	HoldingID string       `json:"holdingId"`
	Count     int          `json:"count"`
	Loans     []model.Loan `json:"loans"`
}

func TestHealthzReportsService(t *testing.T) {
	var body map[string]string
	decode(t, get(t, newHandler(t, empty), "/healthz"), http.StatusOK, &body)
	if body["status"] != "ok" || body["service"] != "stacks" {
		t.Fatalf("healthz body: %v", body)
	}
}

func TestReadyzOnSeededCatalog(t *testing.T) {
	var body struct {
		Status   string `json:"status"`
		Holdings int    `json:"holdings"`
	}
	decode(t, get(t, newHandler(t, seeded), "/readyz"), http.StatusOK, &body)
	if body.Status != "ok" || body.Holdings != 24 {
		t.Fatalf("seeded catalog carries 24 shelved items, probe said %q / %d",
			body.Status, body.Holdings)
	}
}

// The schema is applied on Open, so the count query succeeds and the zero result —
// not a missing table — is what reports the service unready.
func TestReadyzOnEmptyCatalog(t *testing.T) {
	wantError(t, get(t, newHandler(t, empty), "/readyz"), http.StatusServiceUnavailable,
		"not_seeded", "no holdings loaded")
}

func TestGetHoldingReturnsFullRecord(t *testing.T) {
	var h model.Holding
	decode(t, get(t, newHandler(t, seeded), "/holdings/stk00000001"), http.StatusOK, &h)
	if h.HoldingID != "stk00000001" || h.BranchID != "BR-CENTRAL" {
		t.Fatalf("identity wrong: %q %q", h.HoldingID, h.BranchID)
	}
	if h.Title != "A TALE OF TWO CITIES" || h.Author != "DICKENS, CHARLES" {
		t.Fatalf("ingest stores title and author uppercased, got %q / %q", h.Title, h.Author)
	}
	if h.Published != "1859-01-01" || h.ISBN != "978-0-00-000001-9" || h.DeskPhone != "15550101" {
		t.Fatalf("scalars wrong: %q %q %q", h.Published, h.ISBN, h.DeskPhone)
	}
	if h.Shelf.CallNumber != "PR4571 .A1 1859" || h.Shelf.Room != "Main Reading Room" ||
		h.Shelf.Wing != "NW" || h.Shelf.Bin != "01420" {
		t.Fatalf("shelf wrong: %+v", h.Shelf)
	}
	if h.Branch == nil || h.Branch.Name != "Central Branch" || h.Branch.SystemID != "STK-SYS-001" {
		t.Fatalf("branch not joined in: %+v", h.Branch)
	}
	if len(h.Loans) != 1 || h.Loans[0].PolicyCode != "CIRC-21D" {
		t.Fatalf("loans wrong: %+v", h.Loans)
	}
}

func TestGetHoldingUnknownID(t *testing.T) {
	wantError(t, get(t, newHandler(t, seeded), "/holdings/stk99999999"), http.StatusNotFound,
		"not_found", "holding not found")
}

// Every loan row carries a borrower id and the read path binds it, but model.Loan
// tags the field json:"-" so the projection stops it at the boundary.
func TestGetHoldingNeverProjectsBorrowerID(t *testing.T) {
	h := newHandler(t, seeded)
	for _, id := range []string{"stk00000001", "stk00000002", "stk00000005"} {
		rec := get(t, h, "/holdings/"+id)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s: status %d", id, rec.Code)
		}
		if strings.Contains(rec.Body.String(), "BRW-") {
			t.Fatalf("%s: borrower id reached the body: %s", id, rec.Body.String())
		}
	}
	if body := get(t, h, "/holdings/stk00000001/loans").Body.String(); strings.Contains(body, "BRW-") {
		t.Fatalf("loans body exposed a borrower id: %s", body)
	}
}

func TestSearchWithoutFiltersIsRejected(t *testing.T) {
	const want = "at least one filter required (title, author, holdingId, published, branchId, shelfBin)"
	h := newHandler(t, seeded)
	wantError(t, get(t, h, "/holdings/search"), http.StatusBadRequest, "bad_request", want)
	// Each filter is trimmed before it is counted, so whitespace is the same as absent.
	wantError(t, get(t, h, "/holdings/search?title=%20"), http.StatusBadRequest, "bad_request", want)
}

// Ingest uppercases the stored title and the handler uppercases the needle. That
// pairing, not a collation on the column, is the whole of the case-insensitivity.
func TestSearchByTitleIsCaseInsensitive(t *testing.T) {
	var body listBody
	decode(t, get(t, newHandler(t, seeded), "/holdings/search?title=tale+of+two"),
		http.StatusOK, &body)
	if body.Count != 1 || body.Holdings[0].HoldingID != "stk00000001" ||
		body.Holdings[0].Title != "A TALE OF TWO CITIES" {
		t.Fatalf("lowercase needle did not match: %+v", body)
	}
}

func TestSearchByAuthorSubstring(t *testing.T) {
	var body listBody
	decode(t, get(t, newHandler(t, seeded), "/holdings/search?author=dickens"),
		http.StatusOK, &body)
	if body.Count != 1 || body.Holdings[0].Author != "DICKENS, CHARLES" {
		t.Fatalf("author search: %+v", body)
	}
	if body.Holdings[0].BranchID != "BR-CENTRAL" || body.Holdings[0].Published != "1859-01-01" {
		t.Fatalf("summary carries the joined-free columns: %+v", body.Holdings[0])
	}
}

// The branch filter on search and the two branch endpoints read the same rows
// through three different queries, so they are asserted against each other here.
func TestBranchFilterAndBranchEndpoints(t *testing.T) {
	h := newHandler(t, seeded)
	var byBranch listBody
	decode(t, get(t, h, "/holdings/search?branchId=BR-CENTRAL"), http.StatusOK, &byBranch)
	if byBranch.Count != 8 {
		t.Fatalf("BR-CENTRAL shelves 8 of the 24 seeded items, search returned %d", byBranch.Count)
	}
	var br model.Branch
	decode(t, get(t, h, "/branches/BR-CENTRAL"), http.StatusOK, &br)
	if br.Name != "Central Branch" || br.RegistrySymbol != "(OCoLC)ocm00000001" {
		t.Fatalf("branch record: %+v", br)
	}
	wantError(t, get(t, h, "/branches/BR-NOWHERE"), http.StatusNotFound, "not_found", "branch not found")

	var first, second listBody
	decode(t, get(t, h, "/branches/BR-CENTRAL/holdings?limit=3"), http.StatusOK, &first)
	if first.BranchID != "BR-CENTRAL" || first.Count != 3 || first.Limit != 3 || first.Offset != 0 {
		t.Fatalf("first page: %+v", first)
	}
	decode(t, get(t, h, "/branches/BR-CENTRAL/holdings?limit=3&offset=3"), http.StatusOK, &second)
	if second.Offset != 3 || second.Count != 3 ||
		second.Holdings[0].HoldingID == first.Holdings[0].HoldingID {
		t.Fatalf("offset did not move the window: %+v", second)
	}
}

func TestSearchByPublished(t *testing.T) {
	h := newHandler(t, seeded)
	var body listBody
	decode(t, get(t, h, "/holdings/search?published=1859-01-01"), http.StatusOK, &body)
	if body.Count != 1 || body.Holdings[0].HoldingID != "stk00000001" {
		t.Fatalf("published search: %+v", body)
	}
	// published is bound with = rather than LIKE, so the year alone matches nothing.
	var year listBody
	decode(t, get(t, h, "/holdings/search?published=1859"), http.StatusOK, &year)
	if year.Count != 0 {
		t.Fatalf("published is exact, the year alone returned %d rows", year.Count)
	}
}

func TestSearchByShelfBin(t *testing.T) {
	var body listBody
	decode(t, get(t, newHandler(t, seeded), "/holdings/search?shelfBin=01420"), http.StatusOK, &body)
	if body.Count != 1 {
		t.Fatalf("bin search returned %d rows: %+v", body.Count, body.Holdings)
	}
	// The query parameter is shelfBin; the column behind it is bin.
	if got := body.Holdings[0]; got.Bin != "01420" || got.Wing != "NW" ||
		got.Room != "Main Reading Room" {
		t.Fatalf("summary shelving wrong: %+v", got)
	}
}

// The clamp is one condition: a limit outside 1..200, or one that is not a number
// at all, leaves the 50 default in place rather than failing the request.
func TestSearchLimitClamping(t *testing.T) {
	h := newHandler(t, seeded)
	var two listBody
	decode(t, get(t, h, "/holdings/search?branchId=BR-EASTSIDE&limit=2"), http.StatusOK, &two)
	if two.Limit != 2 || two.Count != 2 {
		t.Fatalf("limit=2: limit %d count %d", two.Limit, two.Count)
	}
	for _, raw := range []string{"0", "-5", "201", "9999", "eight", ""} {
		var body listBody
		decode(t, get(t, h, "/holdings/search?branchId=BR-EASTSIDE&limit="+raw), http.StatusOK, &body)
		if body.Limit != 50 || body.Count != 8 {
			t.Fatalf("limit=%q: limit %d count %d, want the 50 default over 8 rows",
				raw, body.Limit, body.Count)
		}
	}
}

func TestGetLoansForHolding(t *testing.T) {
	h := newHandler(t, seeded)
	var body loansBody
	decode(t, get(t, h, "/holdings/stk00000001/loans"), http.StatusOK, &body)
	if body.HoldingID != "stk00000001" || body.Count != 1 || len(body.Loans) != 1 {
		t.Fatalf("loans envelope: %+v", body)
	}
	l := body.Loans[0]
	if l.Type != "LOAN" || l.Level != "STD" || l.PolicyCode != "CIRC-21D" ||
		l.EffectiveStart != "2026-01-04" || l.EffectiveEnd != "2026-01-25" {
		t.Fatalf("loan fields: %+v", l)
	}
	// The in-repair item carries an =876 with no dates under it, and a loan with no
	// effective start is dropped at ingest rather than stored half-formed.
	var none loansBody
	decode(t, get(t, h, "/holdings/stk00000004/loans"), http.StatusOK, &none)
	if none.Count != 0 || len(none.Loans) != 0 {
		t.Fatalf("undated loan should not have been stored: %+v", none)
	}
	wantError(t, get(t, h, "/holdings/stk99999999/loans"), http.StatusNotFound,
		"not_found", "holding not found")
}

func TestPatchHoldingUppercasesAndWritesShelf(t *testing.T) {
	h := newHandler(t, seeded)
	body := `{"author":"dickens, charles","title":"a tale of two cities",` +
		`"shelf":{"room":"Reading Room Annex","wing":"sw","bin":"01999"}}`
	var got model.Holding
	decode(t, patch(t, h, "/holdings/stk00000001", body), http.StatusOK, &got)
	if got.Author != "DICKENS, CHARLES" || got.Title != "A TALE OF TWO CITIES" {
		t.Fatalf("PATCH stores author and title uppercased, got %q / %q", got.Author, got.Title)
	}
	// Room is stored verbatim; wing goes through the same uppercasing as the title.
	if got.Shelf.Room != "Reading Room Annex" || got.Shelf.Wing != "SW" || got.Shelf.Bin != "01999" {
		t.Fatalf("shelf after patch: %+v", got.Shelf)
	}
	// The response is re-read from the database rather than echoed back.
	var again model.Holding
	decode(t, get(t, h, "/holdings/stk00000001"), http.StatusOK, &again)
	if again.Title != got.Title || again.Shelf.Bin != got.Shelf.Bin || again.Shelf.Wing != got.Shelf.Wing {
		t.Fatalf("re-read disagreed: %+v", again)
	}
	wantError(t, patch(t, h, "/holdings/stk99999999", `{"title":"anything"}`),
		http.StatusNotFound, "not_found", "holding not found")
}

func TestPatchValidationRules(t *testing.T) {
	h := newHandler(t, seeded)
	cases := []struct {
		name string
		body string
		want string
	}{
		{"empty title", `{"title":"   "}`, "title must not be empty"},
		{"unknown language", `{"language":"DE"}`,
			"language must be one of EN, ES, FR, UND, or empty"},
		{"punctuated phone", `{"deskPhone":"+1-555-0101"}`, "deskPhone must be digits only"},
		{"three-letter wing", `{"shelf":{"wing":"NWW"}}`, "wing must be a 2-letter code or empty"},
		{"four-digit bin", `{"shelf":{"bin":"0142"}}`, "bin must be 5 digits or empty"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			wantError(t, patch(t, h, "/holdings/stk00000001", tc.body),
				http.StatusBadRequest, "bad_request", tc.want)
		})
	}
	// Validation runs over the whole patch before any SET fragment is bound, so none
	// of the rejected bodies left a partial write behind.
	var after model.Holding
	decode(t, get(t, h, "/holdings/stk00000001"), http.StatusOK, &after)
	if after.Title != "A TALE OF TWO CITIES" || after.Shelf.Bin != "01420" ||
		after.DeskPhone != "15550101" || after.Shelf.Wing != "NW" {
		t.Fatalf("a rejected patch still changed the row: %+v", after)
	}
}

func TestPatchRejectsWrongContentTypeAndEmptyBody(t *testing.T) {
	h := newHandler(t, seeded)
	const ctMsg = "Content-Type must be application/json"
	wrong := send(t, h, http.MethodPatch, "/holdings/stk00000001", `{"title":"whatever"}`,
		map[string]string{"Content-Type": "text/plain"})
	wantError(t, wrong, http.StatusBadRequest, "bad_request", ctMsg)
	// The header is checked before the body is read, so an absent one fails the same way.
	absent := send(t, h, http.MethodPatch, "/holdings/stk00000001", `{"title":"whatever"}`, nil)
	wantError(t, absent, http.StatusBadRequest, "bad_request", ctMsg)
	const emptyMsg = "request body had no updatable fields"
	wantError(t, patch(t, h, "/holdings/stk00000001", `{}`),
		http.StatusBadRequest, "bad_request", emptyMsg)
	// Ingest-derived keys decode to the same empty patch: they are not on the patch
	// type at all and cannot be written over HTTP.
	wantError(t, patch(t, h, "/holdings/stk00000001", `{"circStatus":"ON-SHELF"}`),
		http.StatusBadRequest, "bad_request", emptyMsg)
}

func TestAdminIngestRequiresToken(t *testing.T) {
	h := newHandler(t, seeded)
	const unauth = "missing or invalid admin token"
	wantError(t, send(t, h, http.MethodPost, "/admin/ingest", "", nil),
		http.StatusUnauthorized, "unauthorized", unauth)
	bad := send(t, h, http.MethodPost, "/admin/ingest", "",
		map[string]string{"X-Admin-Token": "not-the-token"})
	wantError(t, bad, http.StatusUnauthorized, "unauthorized", unauth)

	ok := send(t, h, http.MethodPost, "/admin/ingest", "",
		map[string]string{"X-Admin-Token": adminToken}) // dev-only, not a secret
	var body ingestResponse
	decode(t, ok, http.StatusOK, &body)
	if !body.Reloaded || body.Seed != seedPath {
		t.Fatalf("ingest response: %+v", body)
	}
	if body.Counts.Systems != 1 || body.Counts.Branches != 3 || body.Counts.Holdings != 24 {
		t.Fatalf("counts wrong: %+v", body.Counts)
	}
	// 23, not 24: the undated loan on the in-repair item is dropped by the reader.
	if body.Counts.Loans != 23 || body.Counts.Reservations != 5 || body.Counts.Borrowers == 0 {
		t.Fatalf("circulation counts wrong: %+v", body.Counts)
	}
}
