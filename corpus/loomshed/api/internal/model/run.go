// Package model holds the JSON projection of a production run and the
// entities it references. Field order mirrors the column order the handlers
// scan against, same convention as the rest of this service.
package model

type LoomRef struct {
	LoomID   string `json:"loomId"`
	Name     string `json:"name,omitempty"`
	LoomType string `json:"loomType,omitempty"`
}

type LotRef struct {
	LotID       string `json:"lotId"`
	FiberBlend  string `json:"fiberBlend,omitempty"`
	DenierCount int    `json:"denierCount,omitempty"`
}

type OrderRef struct {
	OrderID    string `json:"orderId"`
	FabricSpec string `json:"fabricSpec,omitempty"`
	CustomerID string `json:"customerId,omitempty"`
}

// ShiftOutput is one loom-shift's contribution to a run. PicksPerMinute is
// the average loom speed logged for that shift, not a running total.
type ShiftOutput struct {
	ShiftDate      string  `json:"shiftDate"`
	ShiftCode      string  `json:"shiftCode"`
	OperatorID     string  `json:"operatorId,omitempty"`
	OutputM        float64 `json:"outputM"`
	PicksPerMinute int     `json:"picksPerMinute,omitempty"`
	DowntimeMin    int     `json:"downtimeMin"`
}

// Defect is scoped to the shift it was found on. MetersAt is a fabric
// position, not a timestamp, so it can be checked against the run's woven
// total without touching the shift rows.
type Defect struct {
	DefectID   int64   `json:"defectId"`
	ShiftDate  string  `json:"shiftDate"`
	ShiftCode  string  `json:"shiftCode"`
	DefectType string  `json:"defectType"`
	Severity   int     `json:"severity"`
	MetersAt   float64 `json:"metersAt"`
	Note       string  `json:"note,omitempty"`
	Status     string  `json:"status"`
}

// Run is assembled, not selected: OutputTotalM and DowntimeTotalMin are sums
// over Shifts computed by the handler after the shift rows are loaded, and
// are never stored columns themselves.
type Run struct {
	RunID            string        `json:"runId"`
	LoomID           string        `json:"loomId"`
	Loom             *LoomRef      `json:"loom,omitempty"`
	LotID            string        `json:"lotId"`
	Lot              *LotRef       `json:"lot,omitempty"`
	OrderID          string        `json:"orderId"`
	Order            *OrderRef     `json:"order,omitempty"`
	StartedOn        string        `json:"startedOn"`
	Status           string        `json:"status"`
	OutputTotalM     float64       `json:"outputTotalM"`
	DowntimeTotalMin int           `json:"downtimeTotalMin"`
	Shifts           []ShiftOutput `json:"shifts"`
	Defects          []Defect      `json:"defects"`
}
