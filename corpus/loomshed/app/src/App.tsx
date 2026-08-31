// Root screen: run search on the left, the selected run's detail (and, when
// a defect is under review, its edit form) on the right.
import { useState } from "react";
import {
  ApiError,
  getRun,
  patchDefect,
  searchRuns,
  type DefectPatch,
  type Run,
  type RunSummary,
  type SearchFilters,
} from "./api/client";
import { DefectEditForm } from "./components/DefectEditForm";
import { RunDetail } from "./components/RunDetail";

const EMPTY_FILTERS: SearchFilters = {
  loomId: "",
  lotId: "",
  orderId: "",
  status: "",
  from: "",
  to: "",
  limit: 50,
};

export function App() {
  const [filters, setFilters] = useState<SearchFilters>(EMPTY_FILTERS);
  const [rows, setRows] = useState<RunSummary[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [selected, setSelected] = useState<Run | null>(null);
  const [editingDefectId, setEditingDefectId] = useState<number | null>(null);
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
    setEditingDefectId(null);
    try {
      const res = await searchRuns(filters);
      setRows(res.runs);
      setCount(res.count);
    } catch (err) {
      setRows([]);
      setCount(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const openRun = async (runId: string) => {
    setLoading(true);
    setError(null);
    setEditingDefectId(null);
    try {
      setSelected(await getRun(runId));
    } catch (err) {
      setSelected(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const saveDefect = async (defectId: number, patch: DefectPatch) => {
    if (selected === null) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      setSelected(await patchDefect(selected.runId, defectId, patch));
      setEditingDefectId(null);
    } catch (err) {
      setError(describe(err));
    } finally {
      setSaving(false);
    }
  };

  const resetSearch = () => {
    setFilters(EMPTY_FILTERS);
    setRows([]);
    setCount(null);
    setSelected(null);
    setEditingDefectId(null);
    setError(null);
  };

  const editingDefect = selected?.defects.find((d) => d.defectId === editingDefectId) ?? null;
  const setFilter = (key: keyof SearchFilters, value: string) =>
    setFilters({ ...filters, [key]: value });

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>loomshed</h1>
          <p>Ashcombe Weaving Works</p>
        </div>
        <button type="button" className="btn" onClick={resetSearch}>
          Clear search
        </button>
      </header>
      {error !== null && <p className="error-banner">{error}</p>}

      <main className="app-body">
        <section className="app-column-left">
          <form
            className="search-form"
            onSubmit={(e) => {
              e.preventDefault();
              void runSearch();
            }}
          >
            <label htmlFor="f-loom">Loom</label>
            <input id="f-loom" value={filters.loomId ?? ""} onChange={(e) => setFilter("loomId", e.target.value)} />
            <label htmlFor="f-status">Status</label>
            <input id="f-status" value={filters.status ?? ""} onChange={(e) => setFilter("status", e.target.value)} />
            <label htmlFor="f-from">Started from</label>
            <input id="f-from" type="date" value={filters.from ?? ""} onChange={(e) => setFilter("from", e.target.value)} />
            <label htmlFor="f-to">Started to</label>
            <input id="f-to" type="date" value={filters.to ?? ""} onChange={(e) => setFilter("to", e.target.value)} />
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? "Searching…" : "Search"}
            </button>
          </form>

          {count !== null && <p className="result-count">{count} runs matched</p>}
          {rows.length === 0 ? (
            <p className="empty-note">No runs matched those filters.</p>
          ) : (
            <ul className="run-list">
              {rows.map((row) => (
                <li key={row.runId} className={row.runId === selected?.runId ? "row-selected" : ""} onClick={() => void openRun(row.runId)}>
                  <span>{row.runId}</span>
                  <span>{row.loomId}</span>
                  <span>{row.status}</span>
                  <span>{row.startedOn}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="app-column-right">
          {selected === null && <p className="empty-note">Select a run to see its record.</p>}
          {selected !== null && editingDefect === null && (
            <RunDetail run={selected} onEditDefect={(id) => setEditingDefectId(id)} />
          )}
          {selected !== null && editingDefect !== null && (
            <DefectEditForm
              runId={selected.runId}
              outputTotalM={selected.outputTotalM}
              defect={editingDefect}
              saving={saving}
              onCancel={() => setEditingDefectId(null)}
              onSave={(patch) => void saveDefect(editingDefect.defectId, patch)}
            />
          )}
        </section>
      </main>
    </div>
  );
}
