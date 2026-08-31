// Package model holds the JSON projection of a shelved item. Field order mirrors
// the holdings table column order, which the positional Scan in the handlers relies on.
package model

type Shelf struct {
	CallNumber string `json:"callNumber,omitempty"`
	Room       string `json:"room,omitempty"`
	Wing       string `json:"wing,omitempty"`
	Bin        string `json:"bin,omitempty"`
}

type Branch struct {
	BranchID       string `json:"branchId"`
	Name           string `json:"name"`
	RegistrySymbol string `json:"registrySymbol,omitempty"`
	SystemID       string `json:"systemId,omitempty"`
}

// BorrowerID and PickupBranch are carried for the export builder but never
// projected: borrower identity is not exposed on the holding read path.
type Loan struct {
	Type           string `json:"type"`
	Level          string `json:"level,omitempty"`
	PolicyCode     string `json:"policyCode,omitempty"`
	EffectiveStart string `json:"effectiveStart"`
	EffectiveEnd   string `json:"effectiveEnd,omitempty"`
	BorrowerID     string `json:"-"`
	PickupBranch   string `json:"-"`
}

type Holding struct {
	HoldingID      string  `json:"holdingId"`
	BranchID       string  `json:"branchId"`
	Author         string  `json:"author"`
	Title          string  `json:"title"`
	Published      string  `json:"published"`
	Language       string  `json:"language,omitempty"`
	MaterialCode   string  `json:"materialCode,omitempty"`
	CircStatus     string  `json:"circStatus,omitempty"`
	CollectionCode string  `json:"collectionCode,omitempty"`
	ISBN           string  `json:"isbn,omitempty"`
	DeskPhone      string  `json:"deskPhone,omitempty"`
	Shelf          Shelf   `json:"shelf"`
	Branch         *Branch `json:"branch,omitempty"`
	Loans          []Loan  `json:"loans"`
}
