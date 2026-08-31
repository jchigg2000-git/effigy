// Root screen: search on the left, the selected holding's record on the right.
// All request orchestration and all user-facing error text live in this file.
import { useState } from "react";
import {
  ApiError,
  getHolding,
  patchHolding,
  searchHoldings,
  type Holding,
  type HoldingPatch,
  type HoldingSummary,
  type SearchFilters,
} from "./api/client";
import { logout } from "./auth";
import { HoldingDetail } from "./components/HoldingDetail";
import { HoldingEditForm } from "./components/HoldingEditForm";
import { ResultsTable } from "./components/ResultsTable";
import { SearchForm } from "./components/SearchForm";

const EMPTY_FILTERS: SearchFilters = {
  title: "",
  author: "",
  holdingId: "",
  published: "",
  branchId: "",
  shelfBin: "",
  limit: 50,
};

export function App() {
  const [filters, setFilters] = useState<SearchFilters>(EMPTY_FILTERS);
  const [rows, setRows] = useState<HoldingSummary[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [selected, setSelected] = useState<Holding | null>(null);
  const [editing, setEditing] = useState(false);
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
    setEditing(false);
    try {
      const res = await searchHoldings(filters);
      setRows(res.holdings);
      setCount(res.count);
    } catch (err) {
      setRows([]);
      setCount(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const openHolding = async (holdingId: string) => {
    setLoading(true);
    setError(null);
    setEditing(false);
    try {
      setSelected(await getHolding(holdingId));
    } catch (err) {
      setSelected(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const saveHolding = async (patch: HoldingPatch) => {
    if (selected === null) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      setSelected(await patchHolding(selected.holdingId, patch));
      setEditing(false);
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
    setEditing(false);
    setError(null);
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>stacks</h1>
          <p>Oakhurst County Library System</p>
        </div>
        <button type="button" className="btn" onClick={logout}>
          Sign out
        </button>
      </header>

      {error !== null && (
        <p className="error-banner">{error}</p>
      )}

      <main className="app-body">
        <section className="app-column-left">
          <SearchForm
            filters={filters}
            busy={loading}
            onChange={setFilters}
            onSubmit={runSearch}
            onReset={resetSearch}
          />
          {loading && (
            <p className="loading-note">Working…</p>
          )}
          {count !== null && (
            <p className="result-count">{count} holdings matched</p>
          )}
          <ResultsTable
            rows={rows}
            selectedId={selected ? selected.holdingId : null}
            onSelect={openHolding}
          />
        </section>

        <section className="app-column-right">
          {selected === null && (
            <p className="empty-note">Select a holding to see its record.</p>
          )}
          {selected !== null && !editing && (
            <HoldingDetail
              holding={selected}
              onEdit={() => setEditing(true)}
            />
          )}
          {selected !== null && editing && (
            <HoldingEditForm
              holding={selected}
              saving={saving}
              onCancel={() => setEditing(false)}
              onSave={saveHolding}
            />
          )}
        </section>
      </main>
    </div>
  );
}
