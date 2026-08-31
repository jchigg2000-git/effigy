import type { HoldingSummary } from "../api/client";

interface ResultsTableProps {
  rows: HoldingSummary[];
  selectedId: string | null;
  onSelect: (holdingId: string) => void;
}

export function ResultsTable({ rows, selectedId, onSelect }: ResultsTableProps) {
  if (rows.length === 0) {
    return <p className="empty-note">No holdings matched those filters.</p>;
  }
  return (
    <table className="results-table">
      <thead>
        <tr>
          <th>Holding id</th>
          <th>Title</th>
          <th>Author</th>
          <th>Published</th>
          <th>Branch</th>
          <th>Room</th>
          <th>Wing</th>
          <th>Bin</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.holdingId}
            className={row.holdingId === selectedId ? "row-selected" : ""}
            onClick={() => onSelect(row.holdingId)}
          >
            <td>{row.holdingId}</td>
            <td>{row.title}</td>
            <td>{row.author}</td>
            <td>{row.published}</td>
            <td>{row.branchId}</td>
            <td>{row.room || "—"}</td>
            <td>{row.wing || "—"}</td>
            <td>{row.bin || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
