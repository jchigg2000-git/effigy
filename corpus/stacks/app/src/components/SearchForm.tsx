// Controlled search panel. Query-parameter names are repeated here as literals.
import { hasAnyFilter, type SearchFilters } from "../api/client";

interface SearchFormProps {
  filters: SearchFilters;
  busy: boolean;
  onChange: (next: SearchFilters) => void;
  onSubmit: () => void;
  onReset: () => void;
}

export function SearchForm({
  filters,
  busy,
  onChange,
  onSubmit,
  onReset,
}: SearchFormProps) {
  const ready = hasAnyFilter(filters);

  const setText = (
    key: "title" | "author" | "holdingId" | "published" | "branchId" | "shelfBin",
    value: string,
  ) => {
    const next: SearchFilters = { ...filters };
    next[key] = value;
    onChange(next);
  };

  return (
    <form
      className="search-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <h2>Find holdings</h2>

      <label htmlFor="f-title">Title contains</label>
      <input
        id="f-title"
        type="text"
        value={filters.title ?? ""}
        onChange={(e) => setText("title", e.target.value)}
      />

      <label htmlFor="f-author">Author contains</label>
      <input
        id="f-author"
        type="text"
        value={filters.author ?? ""}
        onChange={(e) => setText("author", e.target.value)}
      />

      <label htmlFor="f-holding-id">Holding id contains</label>
      <input
        id="f-holding-id"
        type="text"
        value={filters.holdingId ?? ""}
        onChange={(e) => setText("holdingId", e.target.value)}
      />

      <label htmlFor="f-published">Published (exact)</label>
      <input
        id="f-published"
        type="text"
        value={filters.published ?? ""}
        onChange={(e) => setText("published", e.target.value)}
      />

      <label htmlFor="f-branch-id">Branch</label>
      <select
        id="f-branch-id"
        value={filters.branchId ?? ""}
        onChange={(e) => setText("branchId", e.target.value)}
      >
        <option value="">Any branch</option>
        <option value="BR-CENTRAL">BR-CENTRAL</option>
        <option value="BR-EASTSIDE">BR-EASTSIDE</option>
        <option value="BR-NORTHGATE">BR-NORTHGATE</option>
      </select>

      <label htmlFor="f-shelf-bin">Shelf bin (exact)</label>
      <input
        id="f-shelf-bin"
        type="text"
        value={filters.shelfBin ?? ""}
        onChange={(e) => setText("shelfBin", e.target.value)}
      />

      <label htmlFor="f-limit">Limit</label>
      <input
        id="f-limit"
        type="number"
        min={1}
        max={200}
        value={filters.limit ?? 50}
        onChange={(e) => onChange({ ...filters, limit: Number(e.target.value) })}
      />

      <div className="search-actions">
        <button type="submit" className="btn btn-primary" disabled={!ready || busy}>
          {busy ? "Searching…" : "Search"}
        </button>
        <button type="button" className="btn" onClick={onReset} disabled={busy}>
          Clear
        </button>
      </div>
      {!ready && (
        <p className="hint">
          At least one filter is required: title, author, holding id, published,
          branch, or shelf bin.
        </p>
      )}
    </form>
  );
}
