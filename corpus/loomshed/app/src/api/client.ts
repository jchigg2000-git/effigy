// Typed client for the loomshed production API.
//
// Requests go through fetch with no wrapper library. Errors are normalised
// into ApiError so callers can branch on status without unwrapping a
// Response. Search parameters are omitted from the query string when empty
// rather than sent blank. Keep this file in step with the Go handlers it
// calls.

const BASE = "/api";

export interface LoomRef {
  loomId: string;
  name?: string;
  loomType?: string;
}

export interface LotRef {
  lotId: string;
  fiberBlend?: string;
  denierCount?: number;
}

export interface OrderRef {
  orderId: string;
  fabricSpec?: string;
  customerId?: string;
}

export interface ShiftOutput {
  shiftDate: string;
  shiftCode: string;
  operatorId?: string;
  outputM: number;
  picksPerMinute?: number;
  downtimeMin: number;
}

export interface Defect {
  defectId: number;
  shiftDate: string;
  shiftCode: string;
  defectType: string;
  severity: number;
  metersAt: number;
  note?: string;
  status: string;
}

export interface Run {
  runId: string;
  loomId: string;
  loom?: LoomRef;
  lotId: string;
  lot?: LotRef;
  orderId: string;
  order?: OrderRef;
  startedOn: string;
  status: string;
  outputTotalM: number;
  downtimeTotalMin: number;
  shifts: ShiftOutput[];
  defects: Defect[];
}

export interface RunSummary {
  runId: string;
  loomId: string;
  lotId: string;
  orderId: string;
  startedOn: string;
  status: string;
}

export interface SearchFilters {
  loomId?: string;
  lotId?: string;
  orderId?: string;
  status?: string;
  from?: string;
  to?: string;
  limit?: number;
}

export interface SearchResponse {
  count: number;
  runs: RunSummary[];
}

export interface DefectPatch {
  status?: string;
  severity?: number;
  note?: string;
  metersAt?: number;
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
  if (f.loomId) params.set("loomId", f.loomId);
  if (f.lotId) params.set("lotId", f.lotId);
  if (f.orderId) params.set("orderId", f.orderId);
  if (f.status) params.set("status", f.status);
  if (f.from) params.set("from", f.from);
  if (f.to) params.set("to", f.to);
  if (f.limit) params.set("limit", String(f.limit));
  return `${BASE}/runs/search?${params.toString()}`;
}

export function hasAnyFilter(f: SearchFilters): boolean {
  return Boolean(f.loomId || f.lotId || f.orderId || f.status || f.from || f.to);
}

export async function searchRuns(f: SearchFilters): Promise<SearchResponse> {
  if (!hasAnyFilter(f)) {
    throw new ApiError(
      400,
      "bad_request",
      "at least one filter required (loomId, lotId, orderId, status, from, to)",
    );
  }
  return request<SearchResponse>(buildSearchUrl(f));
}

export async function getRun(id: string): Promise<Run> {
  return request<Run>(`${BASE}/runs/${encodeURIComponent(id)}`);
}

export async function patchDefect(
  runId: string,
  defectId: number,
  patch: DefectPatch,
): Promise<Run> {
  return request<Run>(
    `${BASE}/runs/${encodeURIComponent(runId)}/defects/${encodeURIComponent(String(defectId))}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
}
