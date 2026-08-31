// Root screen: an airframe/part search on the left, the drilled-down
// component record on the right. All request orchestration and all
// user-facing error text live in this file. There is no standalone results
// table component here — the walk-order listing is inline, since it is only
// ever rendered in this one place.
import { useState } from "react";
import {
  ApiError,
  getComponent,
  patchComponent,
  searchComponents,
  type Component,
  type ComponentPatch,
  type ComponentSearchFilters,
  type ComponentSummary,
} from "./api/client";
import { ComponentDetail } from "./components/ComponentDetail";
import { ComponentEditForm } from "./components/ComponentEditForm";

const EMPTY_FILTERS: ComponentSearchFilters = {
  tailNumber: "",
  category: "",
  partNumber: "",
  serialNumber: "",
  limit: 50,
};

export function App() {
  const [filters, setFilters] = useState<ComponentSearchFilters>(EMPTY_FILTERS);
  const [rows, setRows] = useState<ComponentSummary[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [selected, setSelected] = useState<Component | null>(null);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const describe = (err: unknown): string =>
    err instanceof ApiError ? `${err.code}: ${err.message}` : "the request could not be completed";

  const runSearch = async () => {
    setLoading(true);
    setError(null);
    setSelected(null);
    setEditing(false);
    try {
      const res = await searchComponents(filters);
      setRows(res.components);
      setCount(res.count);
    } catch (err) {
      setRows([]);
      setCount(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const openComponent = async (componentId: string) => {
    setLoading(true);
    setError(null);
    setEditing(false);
    try {
      setSelected(await getComponent(componentId));
    } catch (err) {
      setSelected(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const saveComponent = async (patch: ComponentPatch) => {
    if (selected === null) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      setSelected(await patchComponent(selected.componentId, patch));
      setEditing(false);
    } catch (err) {
      setError(describe(err));
    } finally {
      setSaving(false);
    }
  };

  const setField = (key: keyof ComponentSearchFilters, value: string) =>
    setFilters({ ...filters, [key]: value });

  const resetSearch = () => {
    setFilters(EMPTY_FILTERS);
    setRows([]);
    setCount(null);
    setSelected(null);
    setEditing(false);
    setError(null);
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>tailwatch</h1>
        <p>Fleet airworthiness tracking</p>
      </header>

      {error !== null && <p className="error-banner">{error}</p>}

      <main className="app-body">
        <section className="app-column-left">
          <form className="search-form" onSubmit={(e) => { e.preventDefault(); runSearch(); }}>
            <label htmlFor="f-tail">Tail number</label>
            <input id="f-tail" value={filters.tailNumber} onChange={(e) => setField("tailNumber", e.target.value)} />
            <label htmlFor="f-category">Category</label>
            <input id="f-category" value={filters.category} onChange={(e) => setField("category", e.target.value)} />
            <label htmlFor="f-part">Part number</label>
            <input id="f-part" value={filters.partNumber} onChange={(e) => setField("partNumber", e.target.value)} />
            <label htmlFor="f-serial">Serial number</label>
            <input id="f-serial" value={filters.serialNumber} onChange={(e) => setField("serialNumber", e.target.value)} />
            <button type="submit" className="btn btn-primary" disabled={loading}>Search</button>
            <button type="button" className="btn" onClick={resetSearch} disabled={loading}>Reset</button>
          </form>

          {loading && <p className="loading-note">Working…</p>}
          {count !== null && <p className="result-count">{count} components matched</p>}

          {rows.length === 0 ? (
            <p className="empty-note">No components matched those filters.</p>
          ) : (
            <table className="results-table">
              <thead>
                <tr>
                  <th>Position</th>
                  <th>Label</th>
                  <th>Part</th>
                  <th>Serial</th>
                  <th>Tail</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.componentId}
                    className={row.componentId === selected?.componentId ? "row-selected" : ""}
                    onClick={() => openComponent(row.componentId)}
                  >
                    <td>{row.positionCode}</td>
                    <td>{row.label}</td>
                    <td>{row.partNumber}</td>
                    <td>{row.serialNumber}</td>
                    <td>{row.tailNumber}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="app-column-right">
          {selected === null && (
            <p className="empty-note">Select a component to see its record.</p>
          )}
          {selected !== null && !editing && (
            <ComponentDetail component={selected} onEdit={() => setEditing(true)} />
          )}
          {selected !== null && editing && (
            <ComponentEditForm
              component={selected}
              saving={saving}
              onCancel={() => setEditing(false)}
              onSave={saveComponent}
            />
          )}
        </section>
      </main>
    </div>
  );
}
