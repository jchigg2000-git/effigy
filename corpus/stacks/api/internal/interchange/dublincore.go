// Package interchange projects a holding into a Dublin Core-flavoured JSON
// record set for download.
//
// This is a ONE-WAY export. It exists so a reader can hand somebody a file; it is
// not a posting format, nothing reads it back, and it is not a conformant
// implementation of any metadata standard. The element names borrow from Dublin
// Core and the envelope borrows from record-set conventions, but the profile is
// local to this service and should never be cited as interoperable.
package interchange

import "stacks/internal/model"

type RecordSet struct {
	RecordType string     `json:"recordType"`
	Type       string     `json:"type"`
	Entry      []SetEntry `json:"entry,omitempty"`
}

type SetEntry struct {
	FullURL  string   `json:"fullUrl,omitempty"`
	Resource Resource `json:"resource,omitempty"`
}

// Resource is the closest this profile gets to a tagged union: an entry carries
// exactly one of Record, Collection, or Availability, and the discriminator is the
// RecordType string inside the value rather than anything the type system knows.
// Readers switch on that string; writers are trusted not to lie.
type Resource = any

type Identifier struct {
	System string `json:"system,omitempty"`
	Value  string `json:"value,omitempty"`
}

type TitleStatement struct {
	Text      string `json:"text,omitempty"`
	Statement string `json:"statement,omitempty"`
}

type ContactPoint struct {
	System string `json:"system,omitempty"`
	Value  string `json:"value,omitempty"`
}

type ShelfLocation struct {
	Line []string `json:"line,omitempty"`
	Room string   `json:"room,omitempty"`
	Wing string   `json:"wing,omitempty"`
	Bin  string   `json:"bin,omitempty"`
}

type Reference struct {
	Ref     string `json:"ref,omitempty"`
	Display string `json:"display,omitempty"`
}

type Record struct {
	RecordType string           `json:"recordType"`
	ID         string           `json:"id"`
	Identifier []Identifier     `json:"identifier,omitempty"`
	Title      []TitleStatement `json:"title,omitempty"`
	Creator    string           `json:"creator,omitempty"`
	Language   string           `json:"language,omitempty"`
	Date       string           `json:"date,omitempty"`
	Format     string           `json:"format,omitempty"`
	Contact    []ContactPoint   `json:"contact,omitempty"`
	Location   []ShelfLocation  `json:"location,omitempty"`
}

type Collection struct {
	RecordType string       `json:"recordType"`
	ID         string       `json:"id"`
	Identifier []Identifier `json:"identifier,omitempty"`
	Name       string       `json:"name,omitempty"`
	PartOf     *Reference   `json:"partOf,omitempty"`
}

type Period struct {
	Start string `json:"start,omitempty"`
	End   string `json:"end,omitempty"`
}

type Coding struct {
	System  string `json:"system,omitempty"`
	Code    string `json:"code,omitempty"`
	Display string `json:"display,omitempty"`
}

type CodedTerm struct {
	Coding []Coding `json:"coding,omitempty"`
	Text   string   `json:"text,omitempty"`
}

type AvailabilityClass struct {
	Type  CodedTerm `json:"type,omitempty"`
	Value string    `json:"value,omitempty"`
}

type Availability struct {
	RecordType string              `json:"recordType"`
	ID         string              `json:"id"`
	Status     string              `json:"status"`
	Holder     string              `json:"holder"`
	Item       Reference           `json:"item,omitempty"`
	Kind       CodedTerm           `json:"kind,omitempty"`
	Class      []AvailabilityClass `json:"class,omitempty"`
	Period     Period              `json:"period,omitempty"`
	Custodian  *Reference          `json:"custodian,omitempty"`
}

// mapLanguage narrows the stored code to a three-letter tag. Anything outside the
// four codes the validator accepts is reported as multilingual rather than
// rejected, because an export must never fail on a value the database already holds.
func mapLanguage(code string) string {
	switch code {
	case "EN", "en":
		return "eng"
	case "ES", "es":
		return "spa"
	case "FR", "fr":
		return "fre"
	case "UND", "und":
		return "und"
	case "":
		return ""
	}
	return "mul"
}

// idOrIndex names an entry that has no natural identifier of its own.
func idOrIndex(id string, i int) string {
	if id != "" {
		return id
	}
	return "loan-" + itoa(i)
}

// itoa formats a small integer longhand rather than importing strconv. The only
// integers this file ever formats are loan ordinals, and the import would be the
// only one in the package besides the model types themselves.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

// BuildRecordSet assembles the export. The order of the conditional appends below is
// the contract: a reader diffing two exports of the same item expects entries and
// identifiers in a stable sequence, and nothing here sorts anything. Identifier
// systems are emitted for holding id, isbn, oclc, lccn and branch id; availability
// classes carry a bare code with no system.
func BuildRecordSet(h model.Holding) RecordSet {
	rec := Record{
		RecordType: "Record",
		ID:         h.HoldingID,
		Identifier: []Identifier{{System: "urn:stacks:holding-id", Value: h.HoldingID}},
		Title:      []TitleStatement{{Text: h.Title}},
		Creator:    h.Author,
		Language:   mapLanguage(h.Language),
		Date:       h.Published,
		Format:     h.MaterialCode,
	}
	if h.ISBN != "" {
		rec.Identifier = append(rec.Identifier, Identifier{System: "urn:isbn:", Value: h.ISBN})
	}
	if h.DeskPhone != "" {
		rec.Contact = append(rec.Contact, ContactPoint{System: "phone", Value: h.DeskPhone})
	}
	loc := ShelfLocation{Room: h.Shelf.Room, Wing: h.Shelf.Wing, Bin: h.Shelf.Bin}
	if h.Shelf.CallNumber != "" {
		loc.Line = []string{h.Shelf.CallNumber}
	}
	if loc.Line != nil || loc.Room != "" || loc.Wing != "" || loc.Bin != "" {
		rec.Location = []ShelfLocation{loc}
	}
	entries := []SetEntry{{FullURL: "Record/" + h.HoldingID, Resource: rec}}

	if h.Branch != nil {
		col := Collection{
			RecordType: "Collection",
			ID:         h.Branch.BranchID,
			Name:       h.Branch.Name,
		}
		if h.Branch.RegistrySymbol != "" {
			col.Identifier = append(col.Identifier,
				Identifier{System: "urn:oclc:", Value: h.Branch.RegistrySymbol})
		}
		if h.Branch.SystemID != "" {
			col.Identifier = append(col.Identifier,
				Identifier{System: "urn:lccn:", Value: h.Branch.SystemID})
			col.PartOf = &Reference{Ref: "System/" + h.Branch.SystemID}
		}
		entries = append(entries, SetEntry{
			FullURL:  "Collection/" + h.Branch.BranchID,
			Resource: col,
		})
	}

	for i, l := range h.Loans {
		av := Availability{
			RecordType: "Availability",
			ID:         idOrIndex(l.PolicyCode, i),
			Status:     "active",
			Holder:     h.BranchID,
			Item:       Reference{Ref: "Record/" + h.HoldingID, Display: h.Title},
			Kind: CodedTerm{
				Coding: []Coding{{
					System: "urn:stacks:branch-id",
					Code:   l.PickupBranch,
				}},
				Text: l.Type,
			},
			Period: Period{Start: l.EffectiveStart, End: l.EffectiveEnd},
		}
		if l.Level != "" {
			av.Class = append(av.Class, AvailabilityClass{
				Type: CodedTerm{
					Coding: []Coding{{
						Code:    l.Level,
						Display: "loan level",
					}},
				},
				Value: l.Level,
			})
		}
		if l.PolicyCode != "" {
			av.Class = append(av.Class, AvailabilityClass{
				Type: CodedTerm{
					Coding: []Coding{{
						Code:    l.PolicyCode,
						Display: "circulation policy",
					}},
				},
				Value: l.PolicyCode,
			})
		}
		if h.Branch != nil {
			av.Custodian = &Reference{
				Ref:     "Collection/" + h.Branch.BranchID,
				Display: h.Branch.Name,
			}
		}
		entries = append(entries, SetEntry{
			FullURL:  "Availability/" + idOrIndex(l.PolicyCode, i),
			Resource: av,
		})
	}
	return RecordSet{RecordType: "RecordSet", Type: "collection", Entry: entries}
}
