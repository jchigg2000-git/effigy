// Root screen: contact search on the left, and either the selected contact's
// record or the confirmation form on the right. All request orchestration and
// all user-facing error text live in this file; this domain has no separate
// results-table or search-form component, unlike the library-catalog corpus.
import { useState } from "react";
import {
  ApiError,
  getContact,
  searchContacts,
  submitConfirmation,
  type ConfirmationRequest,
  type ConfirmationResult,
  type Contact,
  type ContactSummary,
  type SearchFilters,
} from "./api/client";
import { ConfirmationForm } from "./components/ConfirmationForm";
import { ContactDetail } from "./components/ContactDetail";

const EMPTY_FILTERS: SearchFilters = {
  band: "",
  mode: "",
  stationId: "",
  from: "",
  to: "",
  limit: 50,
};

export function App() {
  const [filters, setFilters] = useState<SearchFilters>(EMPTY_FILTERS);
  const [rows, setRows] = useState<ContactSummary[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmResult, setConfirmResult] = useState<ConfirmationResult | null>(null);
  const [loading, setLoading] = useState(false);
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
    setConfirming(false);
    try {
      const res = await searchContacts(filters);
      setRows(res.contacts);
      setCount(res.count);
    } catch (err) {
      setRows([]);
      setCount(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const openContact = async (contactId: string) => {
    setLoading(true);
    setError(null);
    setConfirming(false);
    setConfirmResult(null);
    try {
      setSelected(await getContact(contactId));
    } catch (err) {
      setSelected(null);
      setError(describe(err));
    } finally {
      setLoading(false);
    }
  };

  const runConfirmation = async (req: ConfirmationRequest) => {
    setError(null);
    try {
      const result = await submitConfirmation(req);
      setConfirmResult(result);
      setConfirming(false);
      if (result.matchedContactId) {
        setSelected(await getContact(result.matchedContactId));
      }
    } catch (err) {
      setError(describe(err));
    }
  };

  const setText = (key: keyof SearchFilters, value: string) => {
    setFilters({ ...filters, [key]: value });
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>qsolog</h1>
          <p>Contact log, confirmations and award progress</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setConfirming(true)}>
          Log a confirmation
        </button>
      </header>

      {error !== null && <p className="error-banner">{error}</p>}
      {confirmResult !== null && (
        <p className="result-count">confirmation {confirmResult.confirmationId}: {confirmResult.matchStatus}</p>
      )}

      <main className="app-body">
        <section className="app-column-left">
          <form
            className="search-form"
            onSubmit={(e) => {
              e.preventDefault();
              runSearch();
            }}
          >
            <h2>Find contacts</h2>
            <label htmlFor="f-band">Band</label>
            <input id="f-band" value={filters.band ?? ""} onChange={(e) => setText("band", e.target.value)} />
            <label htmlFor="f-mode">Mode</label>
            <input id="f-mode" value={filters.mode ?? ""} onChange={(e) => setText("mode", e.target.value)} />
            <label htmlFor="f-from">From date</label>
            <input id="f-from" value={filters.from ?? ""} onChange={(e) => setText("from", e.target.value)} />
            <label htmlFor="f-to">To date</label>
            <input id="f-to" value={filters.to ?? ""} onChange={(e) => setText("to", e.target.value)} />
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? "Searching…" : "Search"}
            </button>
          </form>

          {count !== null && <p className="result-count">{count} contacts matched</p>}
          {rows.length === 0 ? (
            <p className="empty-note">No contacts matched those filters.</p>
          ) : (
            <table className="results-table">
              <thead>
                <tr>
                  <th>Contact id</th>
                  <th>Worked</th>
                  <th>Band</th>
                  <th>Mode</th>
                  <th>Date</th>
                  <th>Confirmed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.contactId}
                    className={row.contactId === selected?.contactId ? "row-selected" : ""}
                    onClick={() => openContact(row.contactId)}
                  >
                    <td>{row.contactId}</td>
                    <td>{row.workedCallsign}</td>
                    <td>{row.band}</td>
                    <td>{row.mode}</td>
                    <td>{row.contactDate}</td>
                    <td>{row.confirmed ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="app-column-right">
          {confirming && <ConfirmationForm onSubmit={runConfirmation} onCancel={() => setConfirming(false)} />}
          {!confirming && selected === null && <p className="empty-note">Select a contact to see its record.</p>}
          {!confirming && selected !== null && <ContactDetail contact={selected} />}
        </section>
      </main>
    </div>
  );
}
