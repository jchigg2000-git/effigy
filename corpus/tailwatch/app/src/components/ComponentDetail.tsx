// Read-only view of a single tracked component. Renders the record returned
// by getComponent, including the derived remaining-life projection and the
// directive-compliance history embedded on it. Optional fields that are
// absent render as an em dash rather than being hidden, so the layout stays
// stable from one record to the next.
import type { Component } from "../api/client";

interface ComponentDetailProps {
  component: Component;
  onEdit: () => void;
}

// unitLabel turns the server's GOVERNING_UNIT constant into the label next to
// whichever remaining-life figure is closest to zero.
function unitLabel(unit?: string): string {
  switch (unit) {
    case "HOURS":
      return "flight hours";
    case "CYCLES":
      return "flight cycles";
    case "CALENDAR_DAYS":
      return "calendar days";
    default:
      return "—";
  }
}

export function ComponentDetail({ component, onEdit }: ComponentDetailProps) {
  const airframe = component.airframe;
  const remaining = component.remaining;
  const compliance = component.compliance ?? [];
  return (
    <section className="component-detail">
      <div className="component-detail-head">
        <div>
          <h2>{component.label}</h2>
          <p>{component.componentId}</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={onEdit}>
          Edit
        </button>
      </div>

      <dl className="detail-grid">
        <dt>Component id</dt>
        <dd>{component.componentId}</dd>
        <dt>Position</dt>
        <dd>{component.positionCode}</dd>
        <dt>Parent position</dt>
        <dd>{component.parentPositionCode || "—"}</dd>
        <dt>Category</dt>
        <dd>{component.category}</dd>
        <dt>Part number</dt>
        <dd>{component.partNumber}</dd>
        <dt>Serial number</dt>
        <dd>{component.serialNumber}</dd>
        <dt>Installed on</dt>
        <dd>{component.installedOn}</dd>
        <dt>Tail number</dt>
        <dd>{component.tailNumber}</dd>
        <dt>Type designation</dt>
        <dd>{airframe?.typeDesignation || "—"}</dd>
        <dt>Operator code</dt>
        <dd>{airframe?.operatorCode || "—"}</dd>
        <dt>Airframe status</dt>
        <dd>{airframe?.status || "—"}</dd>
      </dl>

      <h3>Remaining life</h3>
      <div className="remaining-grid">
        <div>
          <span>Hours</span>
          <span>{remaining?.remainingHours ?? "—"}</span>
        </div>
        <div>
          <span>Cycles</span>
          <span>{remaining?.remainingCycles ?? "—"}</span>
        </div>
        <div>
          <span>Calendar days</span>
          <span>{remaining?.remainingDays ?? "—"}</span>
        </div>
        <div>
          <span>Governing unit</span>
          <span>{unitLabel(remaining?.governingUnit)}</span>
        </div>
      </div>

      <h3>
        Directive compliance <span className="compliance-count">{compliance.length}</span>
      </h3>
      {compliance.length === 0 ? (
        <p className="empty-note">No directive has been checked against this component.</p>
      ) : (
        <ul className="compliance-list">
          {compliance.map((record, i) => (
            <li key={i}>
              <span>{record.directive.directiveId}</span>
              <span>{record.directive.title}</span>
              <span>{record.method}</span>
              <span>{record.status}</span>
              <span>
                {record.compliedOn} → {record.nextDueOn || "no recurrence"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
