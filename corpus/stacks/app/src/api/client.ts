// Typed client for the stacks inter-branch catalog API.
//
// Requests go through fetch with no wrapper library. Errors are normalised into
// ApiError so callers can branch on status without unwrapping a Response.
// Search parameters are omitted from the query string when empty rather than
// sent blank. Keep this file in step with the Go handlers it calls.

const BASE = "/api";

export interface Shelf {
  callNumber?: string;
  room?: string;
  wing?: string;
  bin?: string;
}

export interface Branch {
  branchId: string;
  name: string;
  registrySymbol?: string;
  systemId?: string;
}

export interface Loan {
  type: string;
  level?: string;
  policyCode?: string;
  effectiveStart: string;
  effectiveEnd?: string;
}

export interface Holding {
  holdingId: string;
  branchId: string;
  author: string;
  title: string;
  published: string;
  language?: string;
  materialCode?: string;
  circStatus?: string;
  collectionCode?: string;
  isbn?: string;
  deskPhone?: string;
  shelf: Shelf;
  branch?: Branch;
  loans: Loan[];
}

export interface HoldingSummary {
  holdingId: string;
  branchId: string;
  author: string;
  title: string;
  published: string;
  room?: string;
  wing?: string;
  bin?: string;
}

export interface SearchFilters {
  title?: string;
  author?: string;
  holdingId?: string;
  published?: string;
  branchId?: string;
  shelfBin?: string;
  limit?: number;
}

export interface SearchResponse {
  count: number;
  holdings: HoldingSummary[];
}

export interface ShelfPatch {
  callNumber?: string;
  room?: string;
  wing?: string;
  bin?: string;
}

export interface HoldingPatch {
  author?: string;
  title?: string;
  language?: string;
  deskPhone?: string;
  shelf?: ShelfPatch;
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
  if (f.title) params.set("title", f.title);
  if (f.author) params.set("author", f.author);
  if (f.holdingId) params.set("holdingId", f.holdingId);
  if (f.published) params.set("published", f.published);
  if (f.branchId) params.set("branchId", f.branchId);
  if (f.shelfBin) params.set("shelfBin", f.shelfBin);
  if (f.limit) params.set("limit", String(f.limit));
  return `${BASE}/holdings/search?${params.toString()}`;
}

export function hasAnyFilter(f: SearchFilters): boolean {
  return Boolean(
    f.title || f.author || f.holdingId || f.published || f.branchId || f.shelfBin,
  );
}

export async function searchHoldings(f: SearchFilters): Promise<SearchResponse> {
  if (!hasAnyFilter(f)) {
    throw new ApiError(
      400,
      "bad_request",
      "at least one filter required (title, author, holdingId, published, branchId, shelfBin)",
    );
  }
  return request<SearchResponse>(buildSearchUrl(f));
}

export async function getHolding(id: string): Promise<Holding> {
  return request<Holding>(`${BASE}/holdings/${encodeURIComponent(id)}`);
}

export async function patchHolding(id: string, patch: HoldingPatch): Promise<Holding> {
  // Bare method name and MIME string, both inline at the call.
  return request<Holding>(`${BASE}/holdings/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export function dcExportUrl(id: string): string {
  return `${BASE}/holdings/${encodeURIComponent(id)}/export/dc`;
}
