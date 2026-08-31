// Read-only view of a single catalog event. Renders whatever getEvent
// returned, including the magnitude estimates and detections an association
// run produced. Optional fields that are absent render as an em dash rather
// than being hidden, so the layout stays stable from one event to the next.
import type { EventDetail as EventDetailData } from "../api/client";

interface EventDetailProps {
  event: EventDetailData;
  onAssociate: () => void;
}

export function EventDetail({ event, onAssociate }: EventDetailProps) {
  const estimates = event.estimates ?? [];
  const detections = event.detections ?? [];
  return (
    <section className="event-detail">
      <div className="event-detail-head">
        <div>
          <h2>{event.eventId}</h2>
          <p>{event.originTime}</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={onAssociate}>
          Associate detections
        </button>
      </div>

      <dl className="detail-grid">
        <dt>Event id</dt>
        <dd>{event.eventId}</dd>
        <dt>Origin time</dt>
        <dd>{event.originTime}</dd>
        <dt>Latitude</dt>
        <dd>{event.latitude.toFixed(4)}</dd>
        <dt>Longitude</dt>
        <dd>{event.longitude.toFixed(4)}</dd>
        <dt>Depth (km)</dt>
        <dd>{event.depthKm.toFixed(1)}</dd>
        <dt>Magnitude</dt>
        <dd>{event.magnitude !== undefined ? event.magnitude.toFixed(2) : "—"}</dd>
        <dt>Magnitude type</dt>
        <dd>{event.magnitudeType || "—"}</dd>
        <dt>Review status</dt>
        <dd>{event.reviewStatus}</dd>
        <dt>Detection count</dt>
        <dd>{event.detectionCount}</dd>
      </dl>

      <h3>
        Magnitude estimates <span className="estimate-count">{estimates.length}</span>
      </h3>
      <p className="section-note">
        One row per contributing channel. The event's own magnitude field above is the
        mean of these values, not a re-derived preferred solution.
      </p>
      {estimates.length === 0 ? (
        <p className="empty-note">No per-channel estimates are recorded against this event.</p>
      ) : (
        <>
          <div className="estimate-list-head">
            <span>Channel</span>
            <span>Type</span>
            <span>Value</span>
            <span>Residual</span>
          </div>
          <ul className="estimate-list">
            {estimates.map((est) => (
              <li key={est.estimateId}>
                <span>{est.channelId}</span>
                <span>{est.magType}</span>
                <span>{est.value.toFixed(2)}</span>
                <span>residual {est.residual.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h3>
        Detections <span className="detection-count">{detections.length}</span>
      </h3>
      <p className="section-note">
        Every detection bound to this event by an association run, across every
        station that reported one, oldest arrival first.
      </p>
      {detections.length === 0 ? (
        <p className="empty-note">No detections are associated with this event.</p>
      ) : (
        <>
          <div className="detection-list-head">
            <span>Station</span>
            <span>Channel</span>
            <span>Phase</span>
            <span>Detected at</span>
            <span>Amplitude</span>
          </div>
          <ul className="detection-list">
            {detections.map((d) => (
              <li key={d.detectionId}>
                <span>{d.stationId}</span>
                <span>{d.channelId}</span>
                <span>{d.phaseHint || "—"}</span>
                <span>{d.detectedAt}</span>
                <span>amp {d.amplitude.toFixed(3)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
