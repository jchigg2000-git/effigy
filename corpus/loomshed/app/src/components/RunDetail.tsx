// Read-only view of a single production run. Renders the record returned by
// getRun: the loom/lot/order it references, the per-shift rows the totals
// are summed from, and the defects logged against it. Each defect row
// offers an edit affordance that hands the defect id up to the parent; this
// component never calls the API itself.
import type { Defect, Run } from "../api/client";

interface RunDetailProps {
  run: Run;
  onEditDefect: (defectId: number) => void;
}

function severityLabel(sev: number): string {
  switch (sev) {
    case 1:
      return "minor";
    case 2:
      return "moderate";
    case 3:
      return "major";
    default:
      return String(sev);
  }
}

export function RunDetail({ run, onEditDefect }: RunDetailProps) {
  const shifts = run.shifts ?? [];
  const defects = run.defects ?? [];
  return (
    <section className="run-detail">
      <div className="run-detail-head">
        <div>
          <h2>{run.runId}</h2>
          <p>{run.status}</p>
        </div>
      </div>

      <dl className="detail-grid">
        <dt>Loom</dt>
        <dd>{run.loom ? `${run.loom.loomId} (${run.loom.loomType || "—"})` : run.loomId}</dd>
        <dt>Yarn lot</dt>
        <dd>{run.lot ? `${run.lot.lotId} — ${run.lot.fiberBlend || "—"}` : run.lotId}</dd>
        <dt>Order</dt>
        <dd>{run.order ? `${run.order.orderId} — ${run.order.fabricSpec || "—"}` : run.orderId}</dd>
        <dt>Started</dt>
        <dd>{run.startedOn}</dd>
        <dt>Output woven</dt>
        <dd>{run.outputTotalM.toFixed(1)} m</dd>
        <dt>Downtime</dt>
        <dd>{run.downtimeTotalMin} min</dd>
      </dl>

      <h3>
        Shifts <span className="shift-count">{shifts.length}</span>
      </h3>
      {shifts.length === 0 ? (
        <p className="empty-note">No shifts are recorded against this run.</p>
      ) : (
        <ul className="shift-list">
          {shifts.map((s, i) => (
            <li key={i}>
              <span>
                {s.shiftDate} / {s.shiftCode}
              </span>
              <span>{s.operatorId || "—"}</span>
              <span>{s.outputM.toFixed(1)} m</span>
              <span>{s.picksPerMinute ? `${s.picksPerMinute} ppm` : "—"}</span>
              <span>{s.downtimeMin} min down</span>
            </li>
          ))}
        </ul>
      )}

      <h3>
        Defects <span className="defect-count">{defects.length}</span>
      </h3>
      {defects.length === 0 ? (
        <p className="empty-note">No defects are logged against this run.</p>
      ) : (
        <ul className="defect-list">
          {defects.map((d: Defect) => (
            <li key={d.defectId}>
              <span>{d.defectType}</span>
              <span>{severityLabel(d.severity)}</span>
              <span>{d.metersAt.toFixed(1)} m</span>
              <span>{d.status}</span>
              <button type="button" className="btn" onClick={() => onEditDefect(d.defectId)}>
                Review
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
