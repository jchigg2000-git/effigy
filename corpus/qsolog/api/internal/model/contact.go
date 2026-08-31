// Package model holds the JSON projection of a logged contact, the station
// that logged it, and the confirmations run against it. Field order mirrors
// the contacts table column order, which the positional Scan in the handlers
// relies on.
package model

// Station is an operator station: the callsign is its own primary key, so
// there is no separate surrogate station id anywhere in this tree.
type Station struct {
	StationID     string `json:"stationId"`
	Callsign      string `json:"callsign"`
	GridSquare    string `json:"gridSquare,omitempty"`
	OperatorClass string `json:"operatorClass,omitempty"`
}

// Confirmation is one inbound claim run against the logbook. MatchedContactID
// is carried for the handler's own bookkeeping but never rendered: a matched
// confirmation is represented to callers by the contact it resolved to, not by
// a second copy of that contact's fields here.
type Confirmation struct {
	ConfirmationID   string `json:"confirmationId"`
	ReceivedFrom     string `json:"receivedFrom"`
	Band             string `json:"band"`
	Mode             string `json:"mode"`
	ContactDate      string `json:"contactDate"`
	MatchStatus      string `json:"matchStatus"`
	LoggedAt         string `json:"loggedAt"`
	MatchedContactID string `json:"-"`
}

type Contact struct {
	ContactID      string         `json:"contactId"`
	StationID      string         `json:"stationId"`
	WorkedCallsign string         `json:"workedCallsign"`
	Band           string         `json:"band"`
	Mode           string         `json:"mode"`
	ContactDate    string         `json:"contactDate"`
	ContactTime    string         `json:"contactTime"`
	SignalSent     string         `json:"signalSent,omitempty"`
	SignalReceived string         `json:"signalReceived,omitempty"`
	GridSquare     string         `json:"gridSquare,omitempty"`
	EntityCode     string         `json:"entityCode,omitempty"`
	ConfirmedOn    string         `json:"confirmedOn,omitempty"`
	Station        *Station       `json:"station,omitempty"`
	Confirmations  []Confirmation `json:"confirmations"`
}
