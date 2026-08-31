import { useState, type FormEvent } from "react";
import type { ExceptionPatch, Read } from "../api/client";

interface FormState {
  toleranceFlag: boolean;
  reason: string;
  requeue: boolean;
}

interface ExceptionFormProps {
  read: Read;
  saving: boolean;
  onCancel: () => void;
  onSave: (patch: ExceptionPatch) => void;
}

const REASON_CODES = ["OUT_OF_TOLERANCE", "METER_STUCK", "ACCESS_BLOCKED", "TRANSCRIPTION_ERROR"];

function initialState(r: Read): FormState {
  return {
    toleranceFlag: r.toleranceFlag,
    reason: r.exceptionReason ?? "",
    requeue: false,
  };
}

// This restates the server-side validator in TypeScript. The authority is
// api/internal/api/reads.go, (*exceptionPatch).validate — the rule below,
// and the exact message text it returns, are a hand-maintained second copy
// of what that method already enforces. Nothing keeps the two in step.
function validate(s: FormState): string | null {
  if (s.reason !== "" && !REASON_CODES.includes(s.reason)) {
    return `reason must be one of ${REASON_CODES.join(", ")}`;
  }
  if (!s.toleranceFlag && s.requeue) {
    return "requeue only makes sense while the read is still flagged";
  }
  return null;
}

// toleranceFlag and requeue are compared by value; reason is compared to the
// read's stored value trimmed. The three checks decide which fields end up
// in the patch body — an unflagged read that is simply re-saved sends none.
function buildPatch(r: Read, s: FormState): ExceptionPatch {
  const patch: ExceptionPatch = {};
  if (s.toleranceFlag !== r.toleranceFlag) {
    patch.toleranceFlag = s.toleranceFlag;
  }
  const reason = s.reason.trim();
  if (reason !== (r.exceptionReason ?? "")) {
    patch.reason = reason;
  }
  if (s.requeue) {
    patch.requeue = true;
  }
  return patch;
}

export function ExceptionForm({ read, saving, onCancel, onSave }: ExceptionFormProps) {
  const [state, setState] = useState<FormState>(() => initialState(read));
  const [error, setError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const problem = validate(state);
    if (problem !== null) {
      setError(problem);
      return;
    }
    setError(null);
    onSave(buildPatch(read, state));
  };

  return (
    <form className="edit-form" onSubmit={submit}>
      <h2>Flag {read.readId}</h2>
      {error && <p className="error-banner">{error}</p>}
      <p className="hint">
        Recorded value {read.readValue} on {read.readDate}, meter {read.meterId}. Flagging
        never changes this value — it only marks the read and, optionally, requeues it.
      </p>

      <label htmlFor="x-tolerance">
        <input
          id="x-tolerance"
          type="checkbox"
          checked={state.toleranceFlag}
          onChange={(e) => setState({ ...state, toleranceFlag: e.target.checked })}
        />
        Outside tolerance
      </label>

      <label htmlFor="x-reason">Reason</label>
      <select
        id="x-reason"
        value={state.reason}
        onChange={(e) => setState({ ...state, reason: e.target.value })}
      >
        <option value="">No reason recorded</option>
        {REASON_CODES.map((code) => (
          <option key={code} value={code}>
            {code}
          </option>
        ))}
      </select>

      <label htmlFor="x-requeue">
        <input
          id="x-requeue"
          type="checkbox"
          checked={state.requeue}
          disabled={!state.toleranceFlag}
          onChange={(e) => setState({ ...state, requeue: e.target.checked })}
        />
        Requeue for a field re-read
      </label>

      <p className="hint">
        Requeuing opens a new pending RE-READ record against this meter and leaves this
        read as the exception on file; it does not overwrite the value above.
      </p>

      <div className="edit-actions">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save exception"}
        </button>
        <button type="button" className="btn" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  );
}
