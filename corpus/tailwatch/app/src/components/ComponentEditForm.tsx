import { useState, type FormEvent } from "react";
import type { Component, ComponentPatch } from "../api/client";

interface FormState {
  partNumber: string;
  serialNumber: string;
  installedOn: string;
}

interface ComponentEditFormProps {
  component: Component;
  saving: boolean;
  onCancel: () => void;
  onSave: (patch: ComponentPatch) => void;
}

function initialState(c: Component): FormState {
  return {
    partNumber: c.partNumber ?? "",
    serialNumber: c.serialNumber ?? "",
    installedOn: "",
  };
}

const partPattern = /^PN-\d{5}$/;
const serialPattern = /^SN-\d{7}$/;
const datePattern = /^\d{4}-\d{2}-\d{2}$/;

// This restates the server-side validator in TypeScript. The authority is
// api/internal/api/components.go, (*componentPatch).validateAndBuild — the
// rules below, and the exact message text they return, are a hand-maintained
// second copy of what that method already enforces. Nothing keeps the two in
// step.
function validate(s: FormState): string | null {
  const partNumber = s.partNumber.trim();
  if (partNumber !== "" && !partPattern.test(partNumber)) {
    return "partNumber must match PN-NNNNN";
  }
  const serialNumber = s.serialNumber.trim();
  if (serialNumber !== "" && !serialPattern.test(serialNumber)) {
    return "serialNumber must match SN-NNNNNNN";
  }
  const installedOn = s.installedOn.trim();
  if (installedOn !== "" && !datePattern.test(installedOn)) {
    return "installedOn must be YYYY-MM-DD";
  }
  return null;
}

// A part swap is a removal followed by an installation: partNumber and
// serialNumber are sent together or not at all here, since a mismatched pair
// (new part, old serial) is not installable on a real airframe. The server
// itself does not enforce that pairing — this is a client-side policy layer
// on top of a looser API. installedOn only ever overrides the server's own
// "now"; leaving it blank lets the server record the swap as happening at
// request time, against the airframe's current hours and cycles.
function buildPatch(c: Component, s: FormState): ComponentPatch {
  const patch: ComponentPatch = {};
  const partNumber = s.partNumber.trim();
  const serialNumber = s.serialNumber.trim();
  if (partNumber !== c.partNumber || serialNumber !== c.serialNumber) {
    patch.partNumber = partNumber;
    patch.serialNumber = serialNumber;
  }
  const installedOn = s.installedOn.trim();
  if (installedOn !== "") {
    patch.installedOn = installedOn;
  }
  return patch;
}

export function ComponentEditForm({
  component,
  saving,
  onCancel,
  onSave,
}: ComponentEditFormProps) {
  const [state, setState] = useState<FormState>(() => initialState(component));
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof FormState, value: string) => {
    const next: FormState = { ...state };
    next[key] = value;
    setState(next);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const problem = validate(state);
    if (problem !== null) {
      setError(problem);
      return;
    }
    const patch = buildPatch(component, state);
    if (Object.keys(patch).length === 0) {
      setError("no changes to save");
      return;
    }
    setError(null);
    onSave(patch);
  };

  return (
    <form className="edit-form" onSubmit={submit}>
      <h2>Replace part on {component.positionCode}</h2>
      {error && <p className="error-banner">{error}</p>}

      <p className="form-note">
        Currently {component.partNumber} / {component.serialNumber}, installed{" "}
        {component.installedOn}.
      </p>

      <label htmlFor="e-part">Part number</label>
      <input
        id="e-part"
        value={state.partNumber}
        onChange={(e) => set("partNumber", e.target.value)}
      />
      <label htmlFor="e-serial">Serial number</label>
      <input
        id="e-serial"
        value={state.serialNumber}
        onChange={(e) => set("serialNumber", e.target.value)}
      />
      <label htmlFor="e-installed">Installed on (optional override)</label>
      <input
        id="e-installed"
        value={state.installedOn}
        onChange={(e) => set("installedOn", e.target.value)}
        placeholder="YYYY-MM-DD"
      />

      <div className="edit-actions">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Record replacement"}
        </button>
        <button type="button" className="btn" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  );
}
