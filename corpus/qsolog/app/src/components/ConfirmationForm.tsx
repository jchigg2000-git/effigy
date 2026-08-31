import { useState, type FormEvent } from "react";
import type { ConfirmationRequest } from "../api/client";

interface FormState {
  stationId: string;
  receivedFrom: string;
  band: string;
  mode: string;
  contactDate: string;
}

interface ConfirmationFormProps {
  onCancel: () => void;
  onSubmit: (req: ConfirmationRequest) => void;
}

const BANDS = ["160m", "80m", "40m", "20m", "17m", "15m", "12m", "10m", "6m", "2m", "70cm"];
const MODES = ["CW", "SSB", "FM", "AM", "FT8", "RTTY", "PSK31"];

const EMPTY_STATE: FormState = {
  stationId: "",
  receivedFrom: "",
  band: BANDS[3],
  mode: MODES[0],
  contactDate: "",
};

// Callsigns in this fixture are drawn from the ITU-unassigned-style prefix
// block X0AAA-X9ZZZ, invented for this corpus so nothing here can collide
// with a real assigned callsign.
const callsignPattern = /^X[0-9][A-Z]{3}$/;
const datePattern = /^\d{4}-\d{2}-\d{2}$/;

// This restates the server-side validator in TypeScript. The authority is
// api/internal/api/contacts.go, handleLogConfirmation — the rules below, and
// the exact message text they return, are a hand-maintained second copy of
// what that handler already enforces. Nothing keeps the two in step.
function validate(s: FormState): string | null {
  if (s.stationId.trim() === "") {
    return "your station's callsign is required";
  }
  if (!callsignPattern.test(s.stationId.trim().toUpperCase())) {
    return "station callsign must look like an invented X-prefix call (e.g. X4ZZQ)";
  }
  if (s.receivedFrom.trim() === "") {
    return "the confirming callsign is required";
  }
  if (!callsignPattern.test(s.receivedFrom.trim().toUpperCase())) {
    return "confirming callsign must look like an invented X-prefix call (e.g. X7BCD)";
  }
  if (!BANDS.includes(s.band)) {
    return "band is not recognised";
  }
  if (!MODES.includes(s.mode)) {
    return "mode is not recognised";
  }
  if (!datePattern.test(s.contactDate.trim())) {
    return "contact date must be YYYY-MM-DD";
  }
  return null;
}

export function ConfirmationForm({ onCancel, onSubmit }: ConfirmationFormProps) {
  const [state, setState] = useState<FormState>(EMPTY_STATE);
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof FormState, value: string) => {
    setState({ ...state, [key]: value });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const problem = validate(state);
    if (problem !== null) {
      setError(problem);
      return;
    }
    setError(null);
    onSubmit({
      stationId: state.stationId.trim().toUpperCase(),
      receivedFrom: state.receivedFrom.trim().toUpperCase(),
      band: state.band,
      mode: state.mode,
      contactDate: state.contactDate.trim(),
    });
  };

  return (
    <form className="confirmation-form" onSubmit={submit}>
      <h2>Log an inbound confirmation</h2>
      <p className="hint">
        Enter what the confirming station claims. A match requires the
        station, the confirming callsign, the band, the mode and the date to
        agree exactly with a logged contact; there is no partial credit.
      </p>
      {error && <p className="error-banner">{error}</p>}

      <label htmlFor="c-station">Your station</label>
      <input
        id="c-station"
        value={state.stationId}
        onChange={(e) => set("stationId", e.target.value)}
      />

      <label htmlFor="c-received-from">Confirming callsign</label>
      <input
        id="c-received-from"
        value={state.receivedFrom}
        onChange={(e) => set("receivedFrom", e.target.value)}
      />

      <label htmlFor="c-band">Band</label>
      <select id="c-band" value={state.band} onChange={(e) => set("band", e.target.value)}>
        {BANDS.map((b) => (
          <option key={b} value={b}>
            {b}
          </option>
        ))}
      </select>

      <label htmlFor="c-mode">Mode</label>
      <select id="c-mode" value={state.mode} onChange={(e) => set("mode", e.target.value)}>
        {MODES.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>

      <label htmlFor="c-date">Contact date</label>
      <input
        id="c-date"
        type="date"
        value={state.contactDate}
        onChange={(e) => set("contactDate", e.target.value)}
      />

      <div className="confirmation-actions">
        <button type="submit" className="btn btn-primary">
          Submit
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
