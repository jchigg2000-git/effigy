// Typed client for the tailwatch fleet airworthiness API.
//
// Requests go through fetch with no wrapper library. Errors are normalised
// into ApiError so callers can branch on status without unwrapping a
// Response. Search parameters are omitted from the query string when empty
// rather than sent blank. Keep this file in step with the Go handlers it
// calls.

const BASE = "/api";

export interface RemainingLife {
  remainingHours?: number;
  remainingCycles?: number;
  remainingDays?: number;
  governingUnit?: string;
}

export interface Airframe {
  tailNumber: string;
  typeDesignation: string;
  operatorCode: string;
  totalHours: number;
  totalCycles: number;
  status: string;
}

export interface Directive {
  directiveId: string;
  title: string;
  issuedBy: string;
  category: string;
}

export interface ComplianceRecord {
  directive: Directive;
  compliedOn: string;
  method: string;
  nextDueOn?: string;
  status: string;
}

export interface ComponentSummary {
  componentId: string;
  tailNumber: string;
  positionCode: string;
  category: string;
  label: string;
  partNumber: string;
  serialNumber: string;
}

export interface Component {
  componentId: string;
  tailNumber: string;
  positionCode: string;
  parentPositionCode?: string;
  category: string;
  label: string;
  partNumber: string;
  serialNumber: string;
  installedOn: string;
  airframe?: Airframe;
  remaining?: RemainingLife;
  compliance: ComplianceRecord[];
}

export interface ComponentSearchFilters {
  tailNumber?: string;
  category?: string;
  partNumber?: string;
  serialNumber?: string;
  limit?: number;
}

export interface ComponentSearchResponse {
  count: number;
  components: ComponentSummary[];
}

export interface ComponentPatch {
  partNumber?: string;
  serialNumber?: string;
  installedOn?: string;
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

export function buildSearchUrl(f: ComponentSearchFilters): string {
  const params = new URLSearchParams();
  if (f.tailNumber) params.set("tailNumber", f.tailNumber);
  if (f.category) params.set("category", f.category);
  if (f.partNumber) params.set("partNumber", f.partNumber);
  if (f.serialNumber) params.set("serialNumber", f.serialNumber);
  if (f.limit) params.set("limit", String(f.limit));
  return `${BASE}/components/search?${params.toString()}`;
}

export function hasAnyFilter(f: ComponentSearchFilters): boolean {
  return Boolean(f.tailNumber || f.category || f.partNumber || f.serialNumber);
}

export async function searchComponents(
  f: ComponentSearchFilters,
): Promise<ComponentSearchResponse> {
  if (!hasAnyFilter(f)) {
    throw new ApiError(
      400,
      "bad_request",
      "at least one filter required (tailNumber, category, partNumber, serialNumber)",
    );
  }
  return request<ComponentSearchResponse>(buildSearchUrl(f));
}

export async function getComponent(id: string): Promise<Component> {
  return request<Component>(`${BASE}/components/${encodeURIComponent(id)}`);
}

export async function patchComponent(
  id: string,
  patch: ComponentPatch,
): Promise<Component> {
  // Bare method name and MIME string, both inline at the call.
  return request<Component>(`${BASE}/components/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}
