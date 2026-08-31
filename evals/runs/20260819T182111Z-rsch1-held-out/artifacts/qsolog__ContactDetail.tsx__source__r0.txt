// Read-only view of a single contact. Renders the record returned by
// getContact, including every confirmation that has been matched against it.
// Optional fields that are absent render as an em dash rather than being
// hidden, so the layout stays stable from one record to the next.
import type { Contact } from "../api/client";

interface ContactDetailProps {
  contact: Contact;
}

export function ContactDetail({ contact }: ContactDetailProps) {
  const confirmations = contact.confirmations ?? [];
  const confirmed = Boolean(contact.confirmedOn);
  return (
    <section className="contact-detail">
      <div className="contact-detail-head">
        <div>
          <h2>{contact.workedCallsign}</h2>
          <p>{contact.contactId}</p>
        </div>
        <span className={confirmed ? "status-confirmed" : "status-unconfirmed"}>
          {confirmed ? "Confirmed" : "Unconfirmed"}
        </span>
      </div>

      <dl className="detail-grid">
        <dt>Contact id</dt>
        <dd>{contact.contactId}</dd>
        <dt>Logging station</dt>
        <dd>{contact.station ? contact.station.callsign : contact.stationId}</dd>
        <dt>Worked callsign</dt>
        <dd>{contact.workedCallsign}</dd>
        <dt>Band</dt>
        <dd>{contact.band}</dd>
        <dt>Mode</dt>
        <dd>{contact.mode}</dd>
        <dt>Date</dt>
        <dd>{contact.contactDate}</dd>
        <dt>Time</dt>
        <dd>{contact.contactTime}</dd>
        <dt>Signal sent</dt>
        <dd>{contact.signalSent || "—"}</dd>
        <dt>Signal received</dt>
        <dd>{contact.signalReceived || "—"}</dd>
        <dt>Grid square</dt>
        <dd>{contact.gridSquare || "—"}</dd>
        <dt>Entity code</dt>
        <dd>{contact.entityCode || "—"}</dd>
        <dt>Confirmed on</dt>
        <dd>{contact.confirmedOn || "—"}</dd>
        <dt>Station grid</dt>
        <dd>{contact.station?.gridSquare || "—"}</dd>
        <dt>Operator class</dt>
        <dd>{contact.station?.operatorClass || "—"}</dd>
      </dl>

      <h3>
        Confirmations <span className="confirmation-count">{confirmations.length}</span>
      </h3>
      {confirmations.length === 0 ? (
        <p className="empty-note">
          No confirmations have matched this contact yet. A confirmation only
          appears here once its station, callsign, band, mode and date agree
          exactly with this record.
        </p>
      ) : (
        <ul className="confirmation-list">
          {confirmations.map((c) => (
            <li key={c.confirmationId}>
              <span>{c.receivedFrom}</span>
              <span>{c.band}</span>
              <span>{c.mode}</span>
              <span>{c.contactDate}</span>
              <span>{c.matchStatus}</span>
              <span>{c.loggedAt}</span>
            </li>
          ))}
        </ul>
      )}

      {/* The award-progress rollup lives at the station level, not here: one
          contact's confirmation says nothing about how many distinct entities
          a station has worked on this band/mode pair. */}
      <p className="hint">
        Award credit for this contact, if any, is reflected in the station's
        award-progress rollup rather than repeated on this page.
      </p>
    </section>
  );
}
