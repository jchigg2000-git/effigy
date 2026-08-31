// Typed client for the tremorline seismic catalog API.
//
// Requests go through fetch with no wrapper library. Errors are normalised
// into ApiError so callers can branch on status without unwrapping a
// Response. Keep this file in step with the Go handlers it calls.

const BASE = "/api";

export interface Channel {
  channelId: string;
  stationId: string;
  channelCode: string;
  sampleRateHz: number;
  azimuthDeg: number;
  dipDeg: number;
  depthM: number;
  validityStart: string;
  validityEnd?: string;
}

export interface Station {
  stationId: string;
  networkCode: string;
  name: string;
  latitude: number;
  longitude: number;
  elevationM: number;
  operator: string;
  status: string;
}

export interface StationSummary {
  stationId: string;
  networkCode: string;
  name: string;
  status: string;
  channelCount: number;
}

export interface StationInventory {
  station: Station;
  channels: Channel[];
}

export interface Detection {
  detectionId: string;
  channelId: string;
  stationId: string;
  detectedAt: string;
  amplitude: number;
  periodS: number;
  phaseHint: string;
  eventId?: string;
}

export interface MagnitudeEstimate {
  estimateId: string;
  eventId: string;
  channelId: string;
  value: number;
  magType: string;
  residual: number;
}

export interface EventSummary {
  eventId: string;
  originTime: string;
  latitude: number;
  longitude: number;
  depthKm: number;
  magnitude?: number;
  magnitudeType?: string;
  reviewStatus: string;
}

export interface EventDetail extends EventSummary {
  detectionCount: number;
  estimates: MagnitudeEstimate[];
  detections: Detection[];
}

export interface CatalogBounds {
  from: string;
  to: string;
  minMagnitude: number;
  maxMagnitude: number;
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
  limit?: number;
}

export interface AssociateRequest {
  detectionIds: string[];
  originTime: string;
  latitude: number;
  longitude: number;
  depthKm: number;
}

export interface SearchResponse {
  count: number;
  events: EventSummary[];
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

export function buildSearchUrl(b: CatalogBounds): string {
  const params = new URLSearchParams();
  params.set("from", b.from);
  params.set("to", b.to);
  params.set("minMagnitude", String(b.minMagnitude));
  params.set("maxMagnitude", String(b.maxMagnitude));
  params.set("minLat", String(b.minLat));
  params.set("maxLat", String(b.maxLat));
  params.set("minLon", String(b.minLon));
  params.set("maxLon", String(b.maxLon));
  if (b.limit) params.set("limit", String(b.limit));
  return `${BASE}/events/search?${params.toString()}`;
}

export async function searchEvents(b: CatalogBounds): Promise<SearchResponse> {
  return request<SearchResponse>(buildSearchUrl(b));
}

export async function getEvent(eventId: string): Promise<EventDetail> {
  return request<EventDetail>(`${BASE}/events/${encodeURIComponent(eventId)}`);
}

export async function associateDetections(req: AssociateRequest): Promise<EventDetail> {
  return request<EventDetail>(`${BASE}/events/associate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function listStations(networkCode?: string): Promise<StationSummary[]> {
  const params = new URLSearchParams();
  if (networkCode) params.set("networkCode", networkCode);
  const res = await request<{ stations: StationSummary[] }>(
    `${BASE}/stations?${params.toString()}`,
  );
  return res.stations;
}

export async function getStationInventory(stationId: string): Promise<StationInventory> {
  return request<StationInventory>(`${BASE}/stations/${encodeURIComponent(stationId)}`);
}
