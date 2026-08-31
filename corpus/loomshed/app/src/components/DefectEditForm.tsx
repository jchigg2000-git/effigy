import { useState, type FormEvent } from "react";
import type { Defect, DefectPatch } from "../api/client";

interface FormState {
  status: string;
  severity: string;
  note: string;
  metersAt: string;
}

interface DefectEditFormProps {
  runId: string;
  outputTotalM: number;
  defect: Defect;
  saving: boolean;
  onCancel: () => void;
  onSave: (patch: DefectPatch) => void;
}

const STATUS_RANK: Record<string, number> = { open: 0, reviewed: 1, resolved: 2 };

function initialState(d: Defect): FormState {
  return {
    status: d.status,
    severity: String(d.severity),
    note: d.note ?? "",
    metersAt: String(d.metersAt),
  };
}

// This restates the server-side validator in TypeScript. The authority is
// api/internal/api/runs.go, (*defectPatch).validateAndBuild — the rules
// below, and the exact message text they return, are a hand-maintained
// second copy of what that method already enforces. Nothing keeps the two
// in step.
function validate(s: FormState, currentStatus: string, outputTotalM: number): string | null {
  const status = s.status.trim().toLowerCase();
  const newRank = STATUS_RANK[status];
  if (newRank === undefined) {
    return "status must be one of open, reviewed, resolved";
  }
  if (newRank < STATUS_RANK[currentStatus]) {
    return `status cannot move backwards from ${currentStatus}`;
  }
  const severity = Number(s.severity);
  if (!Number.isInteger(severity) || severity < 1 || severity > 3) {
    return "severity must be between 1 and 3";
  }
  if (s.note.trim().length > 240) {
    return "note must be 240 characters or fewer";
  }
  const metersAt = Number(s.metersAt);
  if (Number.isNaN(metersAt) || metersAt < 0) {
    return "metersAt must not be negative";
  }
  if (metersAt > outputTotalM) {
    return "metersAt cannot exceed the run's woven output total";
  }
  return null;
}

// Only fields that changed from the loaded defect are sent, same convention
// as the rest of this SPA's edit forms.
function buildPatch(d: Defect, s: FormState): DefectPatch {
  const patch: DefectPatch = {};
  const status = s.status.trim().toLowerCase();
  if (status !== d.status) {
    patch.status = status;
  }
  const severity = Number(s.severity);
  if (severity !== d.severity) {
    patch.severity = severity;
  }
  const note = s.note.trim();
  if (note !== (d.note ?? "")) {
    patch.note = note;
  }
  const metersAt = Number(s.metersAt);
  if (metersAt !== d.metersAt) {
    patch.metersAt = metersAt;
  }
  return patch;
}

export function DefectEditForm({
  runId,
  outputTotalM,
  defect,
  saving,
  onCancel,
  onSave,
}: DefectEditFormProps) {
  const [state, setState] = useState<FormState>(() => initialState(defect));
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof FormState, value: string) => {
    setState({ ...state, [key]: value });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const problem = validate(state, defect.status, outputTotalM);
    if (problem !== null) {
      setError(problem);
      return;
    }
    setError(null);
    onSave(buildPatch(defect, state));
  };

  return (
    <form className="edit-form" onSubmit={submit}>
      <h2>
        Review defect on {runId} — {defect.defectType}
      </h2>
      {error && <p className="error-banner">{error}</p>}

      <label htmlFor="d-status">Status</label>
      <select id="d-status" value={state.status} onChange={(e) => set("status", e.target.value)}>
        <option value="open">open</option>
        <option value="reviewed">reviewed</option>
        <option value="resolved">resolved</option>
      </select>

      <label htmlFor="d-severity">Severity (1-3)</label>
      <input
        id="d-severity"
        type="number"
        min={1}
        max={3}
        value={state.severity}
        onChange={(e) => set("severity", e.target.value)}
      />

      <label htmlFor="d-meters-at">Position (m)</label>
      <input
        id="d-meters-at"
        type="number"
        min={0}
        step="0.1"
        value={state.metersAt}
        onChange={(e) => set("metersAt", e.target.value)}
      />

      <label htmlFor="d-note">Note</label>
      <input id="d-note" value={state.note} onChange={(e) => set("note", e.target.value)} />

      <div className="edit-actions">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button type="button" className="btn" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  );
}
