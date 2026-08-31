import { useState, type FormEvent } from "react";
import type { AssociateRequest } from "../api/client";

interface FormState {
  detectionIds: string;
  originTime: string;
  latitude: string;
  longitude: string;
  depthKm: string;
}

interface AssociationFormProps {
  saving: boolean;
  onCancel: () => void;
  onAssociate: (req: AssociateRequest) => void;
}

const EMPTY_STATE: FormState = {
  detectionIds: "",
  originTime: "",
  latitude: "",
  longitude: "",
  depthKm: "",
};

// This restates the server-side validator in TypeScript. The authority is
// api/internal/api/events.go, handleAssociateDetections — the rules below,
// and the two-station requirement in particular, are a hand-maintained
// second copy of what that handler already enforces. Nothing keeps the two
// in step; the server is the one that can actually see whether a detection
// already belongs to an event.
function validate(s: FormState): string | null {
  const ids = s.detectionIds
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v !== "");
  if (ids.length < 2) {
    return "at least two detection ids are required, comma-separated";
  }
  if (new Set(ids).size !== ids.length) {
    return "detection ids must not repeat";
  }
  if (Number.isNaN(Date.parse(s.originTime))) {
    return "origin time must be a valid date/time";
  }
  const lat = Number(s.latitude);
  if (Number.isNaN(lat) || lat < -90 || lat > 90) {
    return "latitude must be between -90 and 90";
  }
  const lon = Number(s.longitude);
  if (Number.isNaN(lon) || lon < -180 || lon > 180) {
    return "longitude must be between -180 and 180";
  }
  const depth = Number(s.depthKm);
  if (Number.isNaN(depth) || depth < 0) {
    return "depth (km) must be zero or a positive number";
  }
  return null;
}

function buildRequest(s: FormState): AssociateRequest {
  const ids = s.detectionIds
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v !== "");
  return {
    detectionIds: ids,
    originTime: new Date(s.originTime).toISOString(),
    latitude: Number(s.latitude),
    longitude: Number(s.longitude),
    depthKm: Number(s.depthKm),
  };
}

export function AssociationForm({ saving, onCancel, onAssociate }: AssociationFormProps) {
  const [state, setState] = useState<FormState>(EMPTY_STATE);
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
    setError(null);
    onAssociate(buildRequest(state));
  };

  return (
    <form className="association-form" onSubmit={submit}>
      <h2>Associate detections into a new event</h2>
      <p className="section-note">
        Provide a candidate origin and the detections it explains. The
        detections must come from at least two stations; a single station
        reporting a transient is not an event.
      </p>
      {error && <p className="error-banner">{error}</p>}

      <label htmlFor="a-detection-ids">Detection ids (comma-separated)</label>
      <input
        id="a-detection-ids"
        value={state.detectionIds}
        onChange={(e) => set("detectionIds", e.target.value)}
        placeholder="RRA-DET-000001, RRA-DET-000002"
      />
      <label htmlFor="a-origin-time">Origin time</label>
      <input
        id="a-origin-time"
        type="datetime-local"
        value={state.originTime}
        onChange={(e) => set("originTime", e.target.value)}
      />
      <label htmlFor="a-latitude">Latitude</label>
      <input id="a-latitude" value={state.latitude} onChange={(e) => set("latitude", e.target.value)} />
      <label htmlFor="a-longitude">Longitude</label>
      <input id="a-longitude" value={state.longitude} onChange={(e) => set("longitude", e.target.value)} />
      <label htmlFor="a-depth-km">Depth (km)</label>
      <input id="a-depth-km" value={state.depthKm} onChange={(e) => set("depthKm", e.target.value)} />

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Associating…" : "Create event"}
        </button>
        <button type="button" className="btn" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  );
}
