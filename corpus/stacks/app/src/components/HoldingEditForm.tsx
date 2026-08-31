import { useState, type FormEvent } from "react";
import type { Holding, HoldingPatch, ShelfPatch } from "../api/client";

interface FormState {
  author: string;
  title: string;
  language: string;
  deskPhone: string;
  callNumber: string;
  room: string;
  wing: string;
  bin: string;
}

interface HoldingEditFormProps {
  holding: Holding;
  saving: boolean;
  onCancel: () => void;
  onSave: (patch: HoldingPatch) => void;
}

function initialState(h: Holding): FormState {
  const shelf = h.shelf ?? {};
  return {
    author: h.author ?? "",
    title: h.title ?? "",
    language: h.language ?? "",
    deskPhone: h.deskPhone ?? "",
    callNumber: shelf.callNumber ?? "",
    room: shelf.room ?? "",
    wing: shelf.wing ?? "",
    bin: shelf.bin ?? "",
  };
}

// This restates the server-side validator in TypeScript. The authority is
// api/internal/api/holdings.go, (*holdingPatch).validateAndBuild — the rules
// below, and the exact message text they return, are a hand-maintained second
// copy of what that method already enforces. Nothing keeps the two in step.
function validate(s: FormState): string | null {
  if (s.author.trim() === "") {
    return "author must not be empty";
  }
  if (s.title.trim() === "") {
    return "title must not be empty";
  }
  const language = s.language.trim().toUpperCase();
  if (language !== "" && !["EN", "ES", "FR", "UND"].includes(language)) {
    return "language must be one of EN, ES, FR, UND, or empty";
  }
  if (!/^\d*$/.test(s.deskPhone.trim())) {
    return "deskPhone must be digits only";
  }
  const wing = s.wing.trim();
  if (wing !== "" && !/^[A-Za-z]{2}$/.test(wing)) {
    return "wing must be a 2-letter code or empty";
  }
  const bin = s.bin.trim();
  if (bin !== "" && !/^\d{5}$/.test(bin)) {
    return "bin must be 5 digits or empty";
  }
  return null;
}

// author, title, language and wing are compared uppercased because the server
// stores them uppercased; callNumber, room, bin and deskPhone are compared
// trimmed only. The asymmetry decides which fields end up in the patch body.
function buildPatch(h: Holding, s: FormState): HoldingPatch {
  const patch: HoldingPatch = {};
  const author = s.author.trim().toUpperCase();
  if (author !== h.author) {
    patch.author = author;
  }
  const title = s.title.trim().toUpperCase();
  if (title !== h.title) {
    patch.title = title;
  }
  const language = s.language.trim().toUpperCase();
  if (language !== (h.language ?? "")) {
    patch.language = language;
  }
  const deskPhone = s.deskPhone.trim();
  if (deskPhone !== (h.deskPhone ?? "")) {
    patch.deskPhone = deskPhone;
  }

  const stored = h.shelf ?? {};
  const shelf: ShelfPatch = {};
  let touched = false;
  const callNumber = s.callNumber.trim();
  if (callNumber !== (stored.callNumber ?? "")) {
    shelf.callNumber = callNumber;
    touched = true;
  }
  const room = s.room.trim();
  if (room !== (stored.room ?? "")) {
    shelf.room = room;
    touched = true;
  }
  const wing = s.wing.trim().toUpperCase();
  if (wing !== (stored.wing ?? "")) {
    shelf.wing = wing;
    touched = true;
  }
  const bin = s.bin.trim();
  if (bin !== (stored.bin ?? "")) {
    shelf.bin = bin;
    touched = true;
  }
  if (touched) {
    patch.shelf = shelf;
  }
  return patch;
}

export function HoldingEditForm({
  holding,
  saving,
  onCancel,
  onSave,
}: HoldingEditFormProps) {
  const [state, setState] = useState<FormState>(() => initialState(holding));
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
    onSave(buildPatch(holding, state));
  };

  return (
    <form className="edit-form" onSubmit={submit}>
      <h2>Edit {holding.holdingId}</h2>
      {error && <p className="error-banner">{error}</p>}

      <label htmlFor="e-author">Author</label>
      <input id="e-author" value={state.author} onChange={(e) => set("author", e.target.value)} />
      <label htmlFor="e-title">Title</label>
      <input id="e-title" value={state.title} onChange={(e) => set("title", e.target.value)} />
      <label htmlFor="e-language">Language</label>
      <input id="e-language" value={state.language} onChange={(e) => set("language", e.target.value)} />
      <label htmlFor="e-desk-phone">Desk phone</label>
      <input id="e-desk-phone" value={state.deskPhone} onChange={(e) => set("deskPhone", e.target.value)} />

      <h3>Shelf</h3>
      <label htmlFor="e-call-number">Call number</label>
      <input id="e-call-number" value={state.callNumber} onChange={(e) => set("callNumber", e.target.value)} />
      <label htmlFor="e-room">Room</label>
      <input id="e-room" value={state.room} onChange={(e) => set("room", e.target.value)} />
      <label htmlFor="e-wing">Wing</label>
      <input id="e-wing" value={state.wing} onChange={(e) => set("wing", e.target.value)} />
      <label htmlFor="e-bin">Bin</label>
      <input id="e-bin" value={state.bin} onChange={(e) => set("bin", e.target.value)} />

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
