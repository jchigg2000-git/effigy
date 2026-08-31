// Read-only view of a single read. Renders the record returned by getRead,
// including the consumption interval computed against the meter's prior
// trusted read when one exists. Optional fields render as an em dash rather
// than being hidden, so the layout stays stable from one read to the next.
import type { Read } from "../api/client";

interface ReadDetailProps {
  read: Read;
  onFlag: () => void;
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

// The server returns a total charge, not a per-unit rate; the average shown
// here is derived client-side purely for display and is never sent back.
function formatAverageRate(chargeCents: number, unitsUsed: number): string {
  if (unitsUsed <= 0) {
    return "—";
  }
  return `${formatCents(Math.round(chargeCents / unitsUsed))} / unit`;
}

const READ_TYPE_NOTES: Record<string, string> = {
  SCHEDULED: "Taken on the normal route pass.",
  "RE-READ": "Taken to close out a prior exception; not a scheduled pass.",
  ESTIMATED: "No register value collected; excluded from consumption intervals.",
};

export function ReadDetail({ read, onFlag }: ReadDetailProps) {
  const sp = read.servicePoint;
  const consumption = read.consumption;
  const typeNote = READ_TYPE_NOTES[read.readType] ?? "";
  return (
    <section className="read-detail">
      <div className="read-detail-head">
        <div>
          <h2>{read.readId}</h2>
          <p>{read.servicePointId}</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={onFlag}>
          Flag / requeue
        </button>
      </div>

      <dl className="detail-grid">
        <dt>Read id</dt>
        <dd>{read.readId}</dd>
        <dt>Meter id</dt>
        <dd>{read.meterId}</dd>
        <dt>Route</dt>
        <dd>{read.routeCode}</dd>
        <dt>Billing cycle</dt>
        <dd>{read.cycleCode}</dd>
        <dt>Read type</dt>
        <dd>{read.readType}</dd>
        <dt>Read value</dt>
        <dd>{read.readValue}</dd>
        <dt>Read date</dt>
        <dd>{read.readDate}</dd>
        <dt>Tolerance</dt>
        <dd>{read.toleranceFlag ? "flagged" : "within tolerance"}</dd>
        <dt>Exception reason</dt>
        <dd>{read.exceptionReason || "—"}</dd>
        <dt>Account reference</dt>
        <dd>{sp?.accountRef || "—"}</dd>
        <dt>Meter serial</dt>
        <dd>{sp?.meter?.serialNumber || "—"}</dd>
        <dt>Meter size</dt>
        <dd>{sp?.meter?.sizeCode || "—"}</dd>
      </dl>

      {typeNote !== "" && <p className="hint">{typeNote}</p>}

      <h3>Consumption interval</h3>
      {consumption === undefined ? (
        <p className="empty-note">
          No prior trusted read on this meter to measure against. The interval appears
          once a second scheduled or re-read reading exists after this one.
        </p>
      ) : (
        <div className="shelf-grid">
          <div>
            <span>Prior read</span>
            <span>{consumption.priorReadId || "—"}</span>
          </div>
          <div>
            <span>Units used</span>
            <span>{consumption.unitsUsed}</span>
          </div>
          <div>
            <span>Tiered charge</span>
            <span>{formatCents(consumption.chargeCents)}</span>
          </div>
          <div>
            <span>Effective rate</span>
            <span>{formatAverageRate(consumption.chargeCents, consumption.unitsUsed)}</span>
          </div>
        </div>
      )}
    </section>
  );
}
