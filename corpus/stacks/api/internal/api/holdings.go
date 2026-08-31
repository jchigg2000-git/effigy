package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"stacks/internal/interchange"
	"stacks/internal/model"
)

// loadHolding pulls a shelved item and the branch that shelves it in one join.
// Fifteen columns come from holdings and four from branches, in the order the
// SELECT list declares them. Nullable columns are coalesced so the scan targets
// can stay non-pointer, and callers get sql.ErrNoRows when the pair does not
// resolve to a shelved item.
func (s *Server) loadHolding(ctx context.Context, holdingID, branchID string) (model.Holding, error) {
	var h model.Holding
	var br model.Branch
	sqlStr := `SELECT h.holding_id, h.branch_id, h.author, h.title, h.published,
	                  COALESCE(h.language,''), COALESCE(h.material_code,''),
	                  COALESCE(h.circ_status,''), COALESCE(h.collection_code,''),
	                  COALESCE(h.isbn,''), COALESCE(h.desk_phone,''),
	                  COALESCE(h.call_number,''), COALESCE(h.room,''),
	                  COALESCE(h.wing,''), COALESCE(h.bin,''),
	                  b.branch_id, b.name, COALESCE(b.registry_symbol,''),
	                  COALESCE(b.system_id,'')
	           FROM holdings h
	           JOIN branches b ON b.branch_id = h.branch_id
	           WHERE h.holding_id = ?`
	args := []any{holdingID}
	if branchID != "" {
		sqlStr += " AND h.branch_id = ?"
		args = append(args, branchID)
	}
	err := s.db.QueryRowContext(ctx, sqlStr, args...).Scan(
		&h.HoldingID, &h.BranchID, &h.Author, &h.Title, &h.Published,
		&h.Language, &h.MaterialCode, &h.CircStatus, &h.CollectionCode, &h.ISBN,
		&h.DeskPhone, &h.Shelf.CallNumber, &h.Shelf.Room, &h.Shelf.Wing, &h.Shelf.Bin,
		&br.BranchID, &br.Name, &br.RegistrySymbol, &br.SystemID)
	if err != nil {
		return model.Holding{}, err
	}
	h.Branch = &br
	h.Loans = []model.Loan{}
	return h, nil
}

// loadLoans reads the circulation history for one item. Borrower identity is read
// off the row but never projected into JSON; the export builder is the only thing
// downstream of here that looks at it.
func (s *Server) loadLoans(ctx context.Context, holdingID string) ([]model.Loan, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT loan_type, COALESCE(loan_level,''),
	                  COALESCE(policy_code,''), effective_start,
	                  COALESCE(effective_end,''), COALESCE(borrower_id,''),
	                  COALESCE(pickup_branch,'')
	           FROM loans WHERE holding_id = ?
	           ORDER BY effective_start, id`, holdingID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.Loan{}
	for rows.Next() {
		var l model.Loan
		if err := rows.Scan(&l.Type, &l.Level, &l.PolicyCode, &l.EffectiveStart,
			&l.EffectiveEnd, &l.BorrowerID, &l.PickupBranch); err != nil {
			return nil, err
		}
		out = append(out, l)
	}
	return out, rows.Err()
}

func (s *Server) handleGetHolding(w http.ResponseWriter, r *http.Request) {
	holdingID := strings.TrimSpace(chi.URLParam(r, "holdingId"))
	branchID := strings.TrimSpace(r.URL.Query().Get("branchId"))
	h, err := s.loadHolding(r.Context(), holdingID, branchID)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "holding not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	loans, err := s.loadLoans(r.Context(), holdingID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	h.Loans = loans
	writeJSON(w, http.StatusOK, h)
}

func (s *Server) handleGetLoans(w http.ResponseWriter, r *http.Request) {
	holdingID := strings.TrimSpace(chi.URLParam(r, "holdingId"))
	var probe string
	err := s.db.QueryRowContext(r.Context(),
		`SELECT holding_id FROM holdings WHERE holding_id = ?`, holdingID).Scan(&probe)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "holding not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	loans, err := s.loadLoans(r.Context(), holdingID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"holdingId": holdingID,
		"count":     len(loans),
		"loans":     loans,
	})
}

type holdingSummary struct {
	HoldingID string `json:"holdingId"`
	BranchID  string `json:"branchId"`
	Author    string `json:"author"`
	Title     string `json:"title"`
	Published string `json:"published"`
	Room      string `json:"room,omitempty"`
	Wing      string `json:"wing,omitempty"`
	Bin       string `json:"bin,omitempty"`
}

// handleSearchHoldings assembles the WHERE clause one optional filter at a time.
// Title and author are stored uppercased by both ingest and PATCH, so uppercasing
// the needle here is the whole of what makes substring matching case-insensitive.
// At the two dozen rows a developer database carries, a full scan costs nothing;
// past ten thousand the answer is an FTS5 virtual table, not a longer WHERE.
func (s *Server) handleSearchHoldings(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	conds := []string{}
	args := []any{}
	if v := strings.TrimSpace(q.Get("title")); v != "" {
		conds = append(conds, "UPPER(title) LIKE ?")
		args = append(args, "%"+strings.ToUpper(v)+"%")
	}
	if v := strings.TrimSpace(q.Get("author")); v != "" {
		conds = append(conds, "UPPER(author) LIKE ?")
		args = append(args, "%"+strings.ToUpper(v)+"%")
	}
	if v := strings.TrimSpace(q.Get("holdingId")); v != "" {
		conds = append(conds, "UPPER(holding_id) LIKE ?")
		args = append(args, "%"+strings.ToUpper(v)+"%")
	}
	if v := strings.TrimSpace(q.Get("published")); v != "" {
		conds = append(conds, "published = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("branchId")); v != "" {
		conds = append(conds, "branch_id = ?")
		args = append(args, v)
	}
	if v := strings.TrimSpace(q.Get("shelfBin")); v != "" {
		conds = append(conds, "bin = ?")
		args = append(args, v)
	}
	if len(conds) == 0 {
		writeError(w, http.StatusBadRequest, "bad_request",
			"at least one filter required (title, author, holdingId, published, branchId, shelfBin)")
		return
	}
	limit := 50
	if n, err := strconv.Atoi(strings.TrimSpace(q.Get("limit"))); err == nil && n > 0 && n <= 200 {
		limit = n
	}
	sqlStr := `SELECT holding_id, branch_id, author, title, published,
	                  COALESCE(room,''), COALESCE(wing,''), COALESCE(bin,'')
	           FROM holdings WHERE ` + strings.Join(conds, " AND ") +
		" ORDER BY title, author LIMIT ?"
	args = append(args, limit)
	rows, err := s.db.QueryContext(r.Context(), sqlStr, args...)
	if err != nil {
		s.serverError(w, err)
		return
	}
	defer rows.Close()
	out := []holdingSummary{}
	for rows.Next() {
		var it holdingSummary
		if err := rows.Scan(&it.HoldingID, &it.BranchID, &it.Author, &it.Title,
			&it.Published, &it.Room, &it.Wing, &it.Bin); err != nil {
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
		"holdings": out,
	})
}

// holdingPatch carries pointers so that "absent from the body" stays
// distinguishable from "present and set to the empty string". Ingest-derived
// fields are not represented here at all and cannot be written over HTTP.
type holdingPatch struct {
	Author    *string     `json:"author"`
	Title     *string     `json:"title"`
	Language  *string     `json:"language"`
	DeskPhone *string     `json:"deskPhone"`
	Shelf     *shelfPatch `json:"shelf"`
}

type shelfPatch struct {
	CallNumber *string `json:"callNumber"`
	Room       *string `json:"room"`
	Wing       *string `json:"wing"`
	Bin        *string `json:"bin"`
}

var wingPattern = regexp.MustCompile(`^[A-Za-z]{2}$`)
var binPattern = regexp.MustCompile(`^\d{5}$`)
var phonePattern = regexp.MustCompile(`^\d*$`)

// validateAndBuild returns the SET fragments, their bind arguments, and a
// bad-request message when a value fails a rule. The fragments and the arguments
// are appended by a closure that writes to both slices from the enclosing scope,
// so the two stay in order by construction rather than by contract.
func (p *holdingPatch) validateAndBuild() ([]string, []any, string) {
	setParts := []string{}
	args := []any{}
	set := func(col string, val any) {
		setParts = append(setParts, col+" = ?")
		args = append(args, val)
	}
	if p.Author != nil {
		v := strings.TrimSpace(*p.Author)
		if v == "" {
			return nil, nil, "author must not be empty"
		}
		set("author", strings.ToUpper(v))
	}
	if p.Title != nil {
		v := strings.TrimSpace(*p.Title)
		if v == "" {
			return nil, nil, "title must not be empty"
		}
		set("title", strings.ToUpper(v))
	}
	if p.Language != nil {
		v := strings.ToUpper(strings.TrimSpace(*p.Language))
		switch v {
		case "EN", "ES", "FR", "UND", "":
			set("language", v)
		default:
			return nil, nil, "language must be one of EN, ES, FR, UND, or empty"
		}
	}
	if p.DeskPhone != nil {
		v := strings.TrimSpace(*p.DeskPhone)
		if !phonePattern.MatchString(v) {
			return nil, nil, "deskPhone must be digits only"
		}
		set("desk_phone", v)
	}
	if p.Shelf != nil {
		if p.Shelf.CallNumber != nil {
			set("call_number", strings.TrimSpace(*p.Shelf.CallNumber))
		}
		if p.Shelf.Room != nil {
			set("room", strings.TrimSpace(*p.Shelf.Room))
		}
		if p.Shelf.Wing != nil {
			v := strings.TrimSpace(*p.Shelf.Wing)
			if v != "" && !wingPattern.MatchString(v) {
				return nil, nil, "wing must be a 2-letter code or empty"
			}
			set("wing", strings.ToUpper(v))
		}
		if p.Shelf.Bin != nil {
			v := strings.TrimSpace(*p.Shelf.Bin)
			if v != "" && !binPattern.MatchString(v) {
				return nil, nil, "bin must be 5 digits or empty"
			}
			set("bin", v)
		}
	}
	return setParts, args, ""
}

func (s *Server) handlePatchHolding(w http.ResponseWriter, r *http.Request) {
	holdingID := strings.TrimSpace(chi.URLParam(r, "holdingId"))
	if ct := r.Header.Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		writeError(w, http.StatusBadRequest, "bad_request", "Content-Type must be application/json")
		return
	}
	var p holdingPatch
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		writeError(w, http.StatusBadRequest, "bad_request", err.Error())
		return
	}
	setParts, setArgs, badReq := p.validateAndBuild()
	if badReq != "" {
		writeError(w, http.StatusBadRequest, "bad_request", badReq)
		return
	}
	if len(setParts) == 0 {
		writeError(w, http.StatusBadRequest, "bad_request", "request body had no updatable fields")
		return
	}
	var probe string
	err := s.db.QueryRowContext(r.Context(),
		`SELECT holding_id FROM holdings WHERE holding_id = ?`, holdingID).Scan(&probe)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "holding not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	setArgs = append(setArgs, holdingID)
	upd := fmt.Sprintf(`UPDATE holdings SET %s WHERE holding_id = ?`, strings.Join(setParts, ", "))
	if _, err := s.db.ExecContext(r.Context(), upd, setArgs...); err != nil {
		s.serverError(w, err)
		return
	}
	h, err := s.loadHolding(r.Context(), holdingID, "")
	if err != nil {
		s.serverError(w, err)
		return
	}
	loans, err := s.loadLoans(r.Context(), holdingID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	h.Loans = loans
	writeJSON(w, http.StatusOK, h)
}

// handleExportDC emits the one-way Dublin Core projection as a download. It is
// not a registry posting format and nothing reads it back.
func (s *Server) handleExportDC(w http.ResponseWriter, r *http.Request) {
	holdingID := strings.TrimSpace(chi.URLParam(r, "holdingId"))
	h, err := s.loadHolding(r.Context(), holdingID, "")
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "not_found", "holding not found")
		return
	}
	if err != nil {
		s.serverError(w, err)
		return
	}
	loans, err := s.loadLoans(r.Context(), holdingID)
	if err != nil {
		s.serverError(w, err)
		return
	}
	h.Loans = loans
	w.Header().Set("Content-Type", "application/dc+json; charset=utf-8")
	w.Header().Set("Content-Disposition", "attachment; filename="+holdingID+".dc.json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(interchange.BuildRecordSet(h))
}
