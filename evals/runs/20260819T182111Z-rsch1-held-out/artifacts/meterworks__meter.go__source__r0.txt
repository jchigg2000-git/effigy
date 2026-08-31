// Package model holds the JSON projection of a metered service point. Field
// order mirrors the reads table column order, which the positional Scan in
// the handlers relies on.
package model

type Meter struct {
	MeterID      string `json:"meterId"`
	SerialNumber string `json:"serialNumber"`
	SizeCode     string `json:"sizeCode,omitempty"`
}

type ServicePoint struct {
	ServicePointID string `json:"servicePointId"`
	RouteCode      string `json:"routeCode"`
	AccountRef     string `json:"accountRef,omitempty"`
	Meter          *Meter `json:"meter,omitempty"`
}

type RateTier struct {
	TierNumber       int `json:"tierNumber"`
	UpperUnits       int `json:"upperUnits,omitempty"`
	RateCentsPerUnit int `json:"rateCentsPerUnit"`
}

// Consumption is derived at read time from the gap between this read and the
// meter's previous trusted read; it is never stored, only computed and
// attached to the response.
type Consumption struct {
	PriorReadID string `json:"priorReadId,omitempty"`
	UnitsUsed   int    `json:"unitsUsed"`
	ChargeCents int    `json:"chargeCents"`
}

type Read struct {
	ReadID          string        `json:"readId"`
	MeterID         string        `json:"meterId"`
	ServicePointID  string        `json:"servicePointId"`
	RouteCode       string        `json:"routeCode"`
	CycleCode       string        `json:"cycleCode"`
	ReadType        string        `json:"readType"`
	ReadValue       int           `json:"readValue"`
	ReadDate        string        `json:"readDate"`
	ToleranceFlag   bool          `json:"toleranceFlag"`
	ExceptionReason string        `json:"exceptionReason,omitempty"`
	Consumption     *Consumption  `json:"consumption,omitempty"`
	ServicePoint    *ServicePoint `json:"servicePoint,omitempty"`
}
