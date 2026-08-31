// Read-only view of a single holding. Renders the record returned by
// getHolding and offers a Dublin Core export link. Optional fields that are
// absent render as an em dash rather than being hidden, so the layout stays
// stable from one record to the next.
import { dcExportUrl, type Holding, type Shelf } from "../api/client";

interface HoldingDetailProps {
  holding: Holding;
  onEdit: () => void;
}

export function HoldingDetail({ holding, onEdit }: HoldingDetailProps) {
  const shelf: Shelf = holding.shelf ?? {};
  const loans = holding.loans ?? [];
  return (
    <section className="holding-detail">
      <div className="holding-detail-head">
        <div>
          <h2>{holding.title}</h2>
          <p>{holding.holdingId}</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={onEdit}>
          Edit
        </button>
      </div>

      <dl className="detail-grid">
        <dt>Holding id</dt>
        <dd>{holding.holdingId}</dd>
        <dt>Branch id</dt>
        <dd>{holding.branchId}</dd>
        <dt>Branch</dt>
        <dd>{holding.branch ? holding.branch.name : holding.branchId}</dd>
        <dt>Author</dt>
        <dd>{holding.author}</dd>
        <dt>Published</dt>
        <dd>{holding.published}</dd>
        <dt>Language</dt>
        <dd>{holding.language || "—"}</dd>
        <dt>Material code</dt>
        <dd>{holding.materialCode || "—"}</dd>
        <dt>Circulation status</dt>
        <dd>{holding.circStatus || "—"}</dd>
        <dt>Collection code</dt>
        <dd>{holding.collectionCode || "—"}</dd>
        <dt>ISBN</dt>
        <dd>{holding.isbn || "—"}</dd>
        <dt>Desk phone</dt>
        <dd>{holding.deskPhone || "—"}</dd>
        <dt>Registry symbol</dt>
        <dd>{holding.branch?.registrySymbol || "—"}</dd>
        <dt>System id</dt>
        <dd>{holding.branch?.systemId || "—"}</dd>
      </dl>

      <h3>Shelf</h3>
      <div className="shelf-grid">
        <div>
          <span>Call number</span>
          <span>{shelf.callNumber || "—"}</span>
        </div>
        <div>
          <span>Room</span>
          <span>{shelf.room || "—"}</span>
        </div>
        <div>
          <span>Wing</span>
          <span>{shelf.wing || "—"}</span>
        </div>
        <div>
          <span>Bin</span>
          <span>{shelf.bin || "—"}</span>
        </div>
      </div>

      <h3>
        Loans <span className="loan-count">{loans.length}</span>
      </h3>
      {loans.length === 0 ? (
        <p className="empty-note">No loans are recorded against this holding.</p>
      ) : (
        <ul className="loan-list">
          {loans.map((loan, i) => (
            <li key={i}>
              <span>{loan.type}</span>
              <span>{loan.level || "—"}</span>
              <span>{loan.policyCode || "—"}</span>
              <span>
                {loan.effectiveStart} → {loan.effectiveEnd || "open"}
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* One-way download link. The SPA builds this URL and never fetches it. */}
      <p className="export-row">
        <a
          className="export-link"
          href={dcExportUrl(holding.holdingId)}
          download={`${holding.holdingId}.dc.json`}
        >
          Download Dublin Core record
        </a>
      </p>
    </section>
  );
}
