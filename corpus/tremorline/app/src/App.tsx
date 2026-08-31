// Root screen: catalog filters and results on the left, the selected event's
// record (or the association form) on the right. No separate results-table
// component: the list is specific enough to this screen that inlining it
// here beats a component with one caller. All request orchestration and all
// user-facing error text live in this file.
import { useState } from "react";
import {
  ApiError,
  associateDetections,
  getEvent,
  searchEvents,
  type AssociateRequest,
  type CatalogBounds,
  type EventDetail as EventDetailData,
  type EventSummary,
} from "./api/client";
import { AssociationForm } from "./components/AssociationForm";
import { EventDetail } from "./components/EventDetail";

const EMPTY_BOUNDS: CatalogBounds = {
  from: "", to: "", minMagnitude: -2, maxMagnitude: 9,
  minLat: -90, maxLat: 90, minLon: -180, maxLon: 180, limit: 50,
};

export function App() {
  const [bounds, setBounds] = useState<CatalogBounds>(EMPTY_BOUNDS);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [selected, setSelected] = useState<EventDetailData | null>(null);
  const [associating, setAssociating] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const describe = (err: unknown): string => {
    if (err instanceof ApiError) {
      return `${err.code}: ${err.message}`;
    }
    return "the request could not be completed";
  };

  const runSearch = async () => {
    setLoading(true);
    setError(null);
    setSelected(null);
    setAssociating(false);
    try {
      const res = await searchEvents(bounds);
      setEvents(res.events);
      setCount(res.count);
    } catch (err) {
      setEvents([]);
      setCount(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const openEvent = async (eventId: string) => {
    setLoading(true);
    setError(null);
    setAssociating(false);
    try {
      setSelected(await getEvent(eventId));
    } catch (err) {
      setSelected(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const runAssociate = async (req: AssociateRequest) => {
    setSaving(true);
    setError(null);
    try {
      setSelected(await associateDetections(req));
      setAssociating(false);
    } catch (err) {
      setError(describe(err));
    } finally {
      setSaving(false);
    }
  };

  const setField = (key: keyof CatalogBounds, value: number | string) => {
    setBounds({ ...bounds, [key]: value });
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>tremorline</h1>
          <p>Ridgeline Regional Array — seismic event catalog</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setAssociating(true)}>
          Associate detections
        </button>
      </header>

      {error !== null && <p className="error-banner">{error}</p>}

      <main className="app-body">
        <section className="app-column-left">
          <form className="bounds-form" onSubmit={(e) => { e.preventDefault(); runSearch(); }}>
            <label htmlFor="f-from">From</label>
            <input id="f-from" type="datetime-local" value={bounds.from}
              onChange={(e) => setField("from", e.target.value)} />
            <label htmlFor="f-to">To</label>
            <input id="f-to" type="datetime-local" value={bounds.to}
              onChange={(e) => setField("to", e.target.value)} />
            <label htmlFor="f-min-mag">Min magnitude</label>
            <input id="f-min-mag" value={bounds.minMagnitude}
              onChange={(e) => setField("minMagnitude", Number(e.target.value))} />
            <label htmlFor="f-max-mag">Max magnitude</label>
            <input id="f-max-mag" value={bounds.maxMagnitude}
              onChange={(e) => setField("maxMagnitude", Number(e.target.value))} />
            <button type="submit" className="btn" disabled={loading}>
              Search
            </button>
          </form>
          {loading && <p className="loading-note">Working…</p>}
          {count !== null && <p className="result-count">{count} events matched</p>}
          {events.length === 0 ? (
            <p className="empty-note">No events matched those bounds.</p>
          ) : (
            <table className="results-table">
              <thead>
                <tr>
                  <th>Event id</th>
                  <th>Origin time</th>
                  <th>Magnitude</th>
                  <th>Depth (km)</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <tr
                    key={ev.eventId}
                    className={ev.eventId === selected?.eventId ? "row-selected" : ""}
                    onClick={() => openEvent(ev.eventId)}
                  >
                    <td>{ev.eventId}</td>
                    <td>{ev.originTime}</td>
                    <td>{ev.magnitude !== undefined ? ev.magnitude.toFixed(2) : "—"}</td>
                    <td>{ev.depthKm.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="app-column-right">
          {associating && (
            <AssociationForm
              saving={saving}
              onCancel={() => setAssociating(false)}
              onAssociate={runAssociate}
            />
          )}
          {!associating && selected === null && (
            <p className="empty-note">Select an event to see its record.</p>
          )}
          {!associating && selected !== null && (
            <EventDetail event={selected} onAssociate={() => setAssociating(true)} />
          )}
        </section>
      </main>
    </div>
  );
}
