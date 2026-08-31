// Typed client for the meterworks metering API.
//
// Requests go through fetch with no wrapper library. Errors are normalised
// into ApiError so callers can branch on status without unwrapping a
// Response. Paging parameters are omitted from the query string when at
// their default rather than sent explicitly. Keep this file in step with
// the Go handlers it calls.

const BASE = "/api";

export interface Meter {
  meterId: string;
  serialNumber: string;
  sizeCode?: string;
}

export interface ServicePoint {
  servicePointId: string;
  routeCode: string;
  accountRef?: string;
  meter?: Meter;
}

export interface Consumption {
  priorReadId?: string;
  unitsUsed: number;
  chargeCents: number;
}

export interface Read {
  readId: string;
  meterId: string;
  servicePointId: string;
  routeCode: string;
  cycleCode: string;
  readType: string;
  readValue: number;
  readDate: string;
  toleranceFlag: boolean;
  exceptionReason?: string;
  consumption?: Consumption;
  servicePoint?: ServicePoint;
}

export interface ReadSummary {
  readId: string;
  servicePointId: string;
  meterId: string;
  readType: string;
  readValue: number;
  readDate: string;
  toleranceFlag: boolean;
}

export interface RouteReadsQuery {
  limit?: number;
  offset?: number;
  cycleCode?: string;
}

export interface RouteReadsResponse {
  routeCode: string;
  count: number;
  limit: number;
  offset: number;
  reads: ReadSummary[];
}

export interface ExceptionPatch {
  toleranceFlag?: boolean;
  reason?: string;
  requeue?: boolean;
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

export function buildRouteReadsUrl(routeCode: string, q: RouteReadsQuery): string {
  const params = new URLSearchParams();
  if (q.limit) params.set("limit", String(q.limit));
  if (q.offset) params.set("offset", String(q.offset));
  if (q.cycleCode) params.set("cycleCode", q.cycleCode);
  return `${BASE}/routes/${encodeURIComponent(routeCode)}/reads?${params.toString()}`;
}

export async function listRouteReads(
  routeCode: string,
  q: RouteReadsQuery = {},
): Promise<RouteReadsResponse> {
  if (routeCode.trim() === "") {
    throw new ApiError(400, "bad_request", "a route code is required");
  }
  return request<RouteReadsResponse>(buildRouteReadsUrl(routeCode, q));
}

export async function getRead(readId: string): Promise<Read> {
  return request<Read>(`${BASE}/reads/${encodeURIComponent(readId)}`);
}

export async function getServicePoint(servicePointId: string): Promise<ServicePoint> {
  return request<ServicePoint>(`${BASE}/service-points/${encodeURIComponent(servicePointId)}`);
}

export async function flagException(readId: string, patch: ExceptionPatch): Promise<Read> {
  return request<Read>(`${BASE}/reads/${encodeURIComponent(readId)}/exception`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}
