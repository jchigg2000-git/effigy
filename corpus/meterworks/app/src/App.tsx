// Root screen: route search on the left, the selected read's detail (or the
// exception form) on the right. All request orchestration and all
// user-facing error text live in this file.
import { useState } from "react";
import {
  ApiError,
  flagException,
  getRead,
  listRouteReads,
  type ExceptionPatch,
  type Read,
  type ReadSummary,
} from "./api/client";
import { ExceptionForm } from "./components/ExceptionForm";
import { ReadDetail } from "./components/ReadDetail";

export function App() {
  const [routeCode, setRouteCode] = useState("");
  const [cycleCode, setCycleCode] = useState("");
  const [rows, setRows] = useState<ReadSummary[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [selected, setSelected] = useState<Read | null>(null);
  const [flagging, setFlagging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const describe = (err: unknown): string =>
    err instanceof ApiError ? `${err.code}: ${err.message}` : "the request could not be completed";

  const runSearch = async () => {
    setLoading(true);
    setError(null);
    setSelected(null);
    setFlagging(false);
    try {
      const res = await listRouteReads(routeCode, { cycleCode: cycleCode || undefined, limit: 50 });
      setRows(res.reads);
      setCount(res.count);
    } catch (err) {
      setRows([]);
      setCount(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const openRead = async (readId: string) => {
    setLoading(true);
    setError(null);
    setFlagging(false);
    try {
      setSelected(await getRead(readId));
    } catch (err) {
      setSelected(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const submitException = async (patch: ExceptionPatch) => {
    if (selected === null) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      setSelected(await flagException(selected.readId, patch));
      setFlagging(false);
    } catch (err) {
      setError(describe(err));
    } finally {
      setSaving(false);
    }
  };

  const resetSearch = () => {
    setRouteCode("");
    setCycleCode("");
    setRows([]);
    setCount(null);
    setSelected(null);
    setFlagging(false);
    setError(null);
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>meterworks</h1>
          <p>Cedar Hollow Municipal Water — route reading &amp; billing console</p>
        </div>
      </header>

      {error !== null && <p className="error-banner">{error}</p>}

      <main className="app-body">
        <section className="app-column-left">
          <form className="route-form" onSubmit={(e) => { e.preventDefault(); runSearch(); }}>
            <h2>Find reads by route</h2>
            <label htmlFor="f-route">Route code</label>
            <input id="f-route" value={routeCode} placeholder="RT0007"
              onChange={(e) => setRouteCode(e.target.value)} />
            <label htmlFor="f-cycle">Billing cycle (optional)</label>
            <input id="f-cycle" value={cycleCode} placeholder="20260701"
              onChange={(e) => setCycleCode(e.target.value)} />
            <div className="search-actions">
              <button type="submit" className="btn btn-primary" disabled={routeCode.trim() === "" || loading}>
                {loading ? "Searching…" : "Search"}
              </button>
              <button type="button" className="btn" onClick={resetSearch} disabled={loading}>
                Clear
              </button>
            </div>
          </form>
          {count !== null && <p className="result-count">{count} reads matched</p>}
          {rows.length === 0 ? (
            <p className="empty-note">No reads matched that route.</p>
          ) : (
            <table className="results-table">
              <thead>
                <tr>
                  <th>Read id</th>
                  <th>Service point</th>
                  <th>Type</th>
                  <th>Value</th>
                  <th>Date</th>
                  <th>Tolerance</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.readId} onClick={() => openRead(row.readId)}
                    className={row.readId === selected?.readId ? "row-selected" : ""}>
                    <td>{row.readId}</td>
                    <td>{row.servicePointId}</td>
                    <td>{row.readType}</td>
                    <td>{row.readValue}</td>
                    <td>{row.readDate}</td>
                    <td>{row.toleranceFlag ? "flagged" : "ok"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="app-column-right">
          {selected === null && <p className="empty-note">Select a read to see its detail.</p>}
          {selected !== null && !flagging && (
            <ReadDetail read={selected} onFlag={() => setFlagging(true)} />
          )}
          {selected !== null && flagging && (
            <ExceptionForm
              read={selected}
              saving={saving}
              onCancel={() => setFlagging(false)}
              onSave={submitException}
            />
          )}
        </section>
      </main>
    </div>
  );
}
