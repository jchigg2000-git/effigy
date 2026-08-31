// Package model holds the JSON projection of the seismic catalog. Field order
// mirrors each table's column order, which the positional Scan calls in the
// handlers rely on.
package model

// NetworkCode values are drawn from the RR0-RR9 block, an invented range
// chosen because no real-world network code registry assigns it to a
// permanent or temporary network. Nothing in this tree should be read as
// identifying an actual seismic network.
type Station struct {
	StationID   string  `json:"stationId"`
	NetworkCode string  `json:"networkCode"`
	Name        string  `json:"name"`
	Latitude    float64 `json:"latitude"`
	Longitude   float64 `json:"longitude"`
	ElevationM  float64 `json:"elevationM"`
	Operator    string  `json:"operator"`
	Status      string  `json:"status"`
}

// Channel is one validity epoch of one channel. A channel that has been
// recalibrated carries more than one row sharing ChannelCode but not
// ChannelID; ValidityEnd is empty for the epoch still in force.
type Channel struct {
	ChannelID     string  `json:"channelId"`
	StationID     string  `json:"stationId"`
	ChannelCode   string  `json:"channelCode"`
	SampleRateHz  float64 `json:"sampleRateHz"`
	AzimuthDeg    float64 `json:"azimuthDeg"`
	DipDeg        float64 `json:"dipDeg"`
	DepthM        float64 `json:"depthM"`
	ValidityStart string  `json:"validityStart"`
	ValidityEnd   string  `json:"validityEnd,omitempty"`
}

type Detection struct {
	DetectionID string  `json:"detectionId"`
	ChannelID   string  `json:"channelId"`
	StationID   string  `json:"stationId"`
	DetectedAt  string  `json:"detectedAt"`
	Amplitude   float64 `json:"amplitude"`
	PeriodS     float64 `json:"periodS"`
	PhaseHint   string  `json:"phaseHint"`
	EventID     string  `json:"eventId,omitempty"`
}

type MagnitudeEstimate struct {
	EstimateID string  `json:"estimateId"`
	EventID    string  `json:"eventId"`
	ChannelID  string  `json:"channelId"`
	Value      float64 `json:"value"`
	MagType    string  `json:"magType"`
	Residual   float64 `json:"residual"`
}

type Event struct {
	EventID        string              `json:"eventId"`
	OriginTime     string              `json:"originTime"`
	Latitude       float64             `json:"latitude"`
	Longitude      float64             `json:"longitude"`
	DepthKm        float64             `json:"depthKm"`
	Magnitude      float64             `json:"magnitude,omitempty"`
	MagnitudeType  string              `json:"magnitudeType,omitempty"`
	ReviewStatus   string              `json:"reviewStatus"`
	DetectionCount int                 `json:"detectionCount"`
	Estimates      []MagnitudeEstimate `json:"estimates,omitempty"`
	Detections     []Detection         `json:"detections,omitempty"`
}
