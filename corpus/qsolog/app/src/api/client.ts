// Typed client for the qsolog contact-logging API.
//
// Requests go through fetch with no wrapper library. Errors are normalised
// into ApiError so callers can branch on status without unwrapping a
// Response. Search parameters are omitted from the query string when empty
// rather than sent blank. Keep this file in step with the Go handlers it
// calls.

const BASE = "/api";

export interface Station {
  stationId: string;
  callsign: string;
  gridSquare?: string;
  operatorClass?: string;
}

export interface Confirmation {
  confirmationId: string;
  receivedFrom: string;
  band: string;
  mode: string;
  contactDate: string;
  matchStatus: string;
  loggedAt: string;
}

export interface Contact {
  contactId: string;
  stationId: string;
  workedCallsign: string;
  band: string;
  mode: string;
  contactDate: string;
  contactTime: string;
  signalSent?: string;
  signalReceived?: string;
  gridSquare?: string;
  entityCode?: string;
  confirmedOn?: string;
  station?: Station;
  confirmations: Confirmation[];
}

export interface ContactSummary {
  contactId: string;
  stationId: string;
  workedCallsign: string;
  band: string;
  mode: string;
  contactDate: string;
  entityCode?: string;
  confirmed: boolean;
}

export interface SearchFilters {
  band?: string;
  mode?: string;
  stationId?: string;
  from?: string;
  to?: string;
  limit?: number;
}

export interface SearchResponse {
  count: number;
  limit: number;
  contacts: ContactSummary[];
}

export interface ConfirmationRequest {
  stationId: string;
  receivedFrom: string;
  band: string;
  mode: string;
  contactDate: string;
}

export interface ConfirmationResult {
  confirmationId: string;
  matchStatus: string;
  matchedContactId?: string;
  contact?: ContactSummary;
}

export interface BandModeProgress {
  band: string;
  mode: string;
  confirmedContacts: number;
  distinctEntities: number;
}

export interface StationSummary {
  stationId: string;
  totalContacts: number;
  distinctBands: number;
  distinctModes: number;
  confirmedContacts: number;
}

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

// Shared transport. Unwraps the {"error":{"code":…,"message":…}} envelope the
// Go service puts on every failure and rethrows it as an ApiError.
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let code = "internal";
    let message = `request failed with status ${res.status}`;
    try {
      const body = await res.json();
      if (body && body.error) {
        code = body.error.code || code;
        message = body.error.message || message;
      }
    } catch {
      // Body was not the JSON error envelope; keep the defaults above.
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

export function buildSearchUrl(f: SearchFilters): string {
  const params = new URLSearchParams();
  if (f.band) params.set("band", f.band);
  if (f.mode) params.set("mode", f.mode);
  if (f.stationId) params.set("stationId", f.stationId);
  if (f.from) params.set("from", f.from);
  if (f.to) params.set("to", f.to);
  if (f.limit) params.set("limit", String(f.limit));
  return `${BASE}/contacts/search?${params.toString()}`;
}

export function hasAnyFilter(f: SearchFilters): boolean {
  return Boolean(f.band || f.mode || f.stationId || f.from || f.to);
}

export async function searchContacts(f: SearchFilters): Promise<SearchResponse> {
  if (!hasAnyFilter(f)) {
    throw new ApiError(
      400,
      "bad_request",
      "at least one filter required (band, mode, stationId, from, to)",
    );
  }
  return request<SearchResponse>(buildSearchUrl(f));
}

export async function getContact(id: string): Promise<Contact> {
  return request<Contact>(`${BASE}/contacts/${encodeURIComponent(id)}`);
}

export async function getStation(id: string): Promise<Station> {
  return request<Station>(`${BASE}/stations/${encodeURIComponent(id)}`);
}

export async function getStationSummary(id: string): Promise<StationSummary> {
  return request<StationSummary>(`${BASE}/stations/${encodeURIComponent(id)}/summary`);
}

export async function submitConfirmation(
  body: ConfirmationRequest,
): Promise<ConfirmationResult> {
  return request<ConfirmationResult>(`${BASE}/confirmations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getAwardProgress(stationId?: string): Promise<BandModeProgress[]> {
  const params = new URLSearchParams();
  if (stationId) params.set("stationId", stationId);
  const res = await request<{ progress: BandModeProgress[] }>(
    `${BASE}/awards/progress?${params.toString()}`,
  );
  return res.progress;
}
