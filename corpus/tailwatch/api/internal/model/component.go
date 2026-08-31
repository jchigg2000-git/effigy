// Package model holds the JSON projection of a tracked airframe component.
// Field order mirrors the components table column order, which the positional
// Scan in the handlers relies on.
package model

// RemainingLife is the whichever-comes-first projection across the three
// parallel units a life-limited part or a recurring interval is tracked in.
// A nil field means that unit has no limit set at all and cannot govern.
// GoverningUnit names whichever unit has consumed the largest fraction of its
// own limit, which is the one that will reach zero first.
type RemainingLife struct {
	RemainingHours  *float64 `json:"remainingHours,omitempty"`
	RemainingCycles *int     `json:"remainingCycles,omitempty"`
	RemainingDays   *int     `json:"remainingDays,omitempty"`
	GoverningUnit   string   `json:"governingUnit,omitempty"`
}

type Airframe struct {
	TailNumber      string  `json:"tailNumber"`
	TypeDesignation string  `json:"typeDesignation"`
	OperatorCode    string  `json:"operatorCode"`
	TotalHours      float64 `json:"totalHours"`
	TotalCycles     int     `json:"totalCycles"`
	Status          string  `json:"status"`
}

// ComponentSummary is the slim projection a hierarchy walk returns: enough to
// render a row and to address the full record, nothing computed.
type ComponentSummary struct {
	ComponentID  string `json:"componentId"`
	TailNumber   string `json:"tailNumber"`
	PositionCode string `json:"positionCode"`
	Category     string `json:"category"`
	Label        string `json:"label"`
	PartNumber   string `json:"partNumber"`
	SerialNumber string `json:"serialNumber"`
}

type Directive struct {
	DirectiveID string `json:"directiveId"`
	Title       string `json:"title"`
	IssuedBy    string `json:"issuedBy"`
	Category    string `json:"category"`
}

// ComplianceRecord carries directive title/issuer rather than just the id so a
// component's compliance list renders without a second round trip.
type ComplianceRecord struct {
	Directive  Directive `json:"directive"`
	CompliedOn string    `json:"compliedOn"`
	Method     string    `json:"method"`
	NextDueOn  string    `json:"nextDueOn,omitempty"`
	Status     string    `json:"status"`
}

type Component struct {
	ComponentID        string             `json:"componentId"`
	TailNumber         string             `json:"tailNumber"`
	PositionCode       string             `json:"positionCode"`
	ParentPositionCode string             `json:"parentPositionCode,omitempty"`
	Category           string             `json:"category"`
	Label              string             `json:"label"`
	PartNumber         string             `json:"partNumber"`
	SerialNumber       string             `json:"serialNumber"`
	InstalledOn        string             `json:"installedOn"`
	Airframe           *Airframe          `json:"airframe,omitempty"`
	Remaining          *RemainingLife     `json:"remaining,omitempty"`
	Compliance         []ComplianceRecord `json:"compliance"`
}
