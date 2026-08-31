-- Schema for the inter-branch catalog. Embedded into the binary by store.go and
-- executed on every Open, so a fresh developer database needs no migration step.

CREATE TABLE IF NOT EXISTS systems (
  system_id TEXT PRIMARY KEY,
  name      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS branches (
  branch_id       TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  registry_symbol TEXT,
  system_id       TEXT REFERENCES systems(system_id)
);

CREATE TABLE IF NOT EXISTS holdings (
  holding_id      TEXT PRIMARY KEY,
  branch_id       TEXT NOT NULL REFERENCES branches(branch_id),
  author          TEXT NOT NULL,
  title           TEXT NOT NULL,
  published       TEXT NOT NULL,
  language        TEXT,
  material_code   TEXT,
  circ_status     TEXT,
  collection_code TEXT,
  isbn            TEXT,
  desk_phone      TEXT,
  call_number     TEXT,
  room            TEXT,
  wing            TEXT,
  bin             TEXT
);
CREATE INDEX IF NOT EXISTS holdings_branch_idx    ON holdings(branch_id);
CREATE INDEX IF NOT EXISTS holdings_title_pub_idx ON holdings(title, published);

CREATE TABLE IF NOT EXISTS loans (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  holding_id      TEXT NOT NULL REFERENCES holdings(holding_id),
  borrower_id     TEXT REFERENCES borrowers(borrower_id),
  loan_type       TEXT NOT NULL,
  loan_level      TEXT,
  policy_code     TEXT,
  pickup_branch   TEXT,
  effective_start TEXT NOT NULL,
  effective_end   TEXT
);
CREATE INDEX IF NOT EXISTS loans_holding_idx ON loans(holding_id);

CREATE TABLE IF NOT EXISTS borrowers (
  borrower_id    TEXT PRIMARY KEY,
  home_branch_id TEXT REFERENCES branches(branch_id)
);

CREATE TABLE IF NOT EXISTS reservations (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  holding_id     TEXT NOT NULL REFERENCES holdings(holding_id),
  borrower_id    TEXT NOT NULL REFERENCES borrowers(borrower_id),
  pickup_branch  TEXT,
  placed_on      TEXT NOT NULL,
  queue_position INTEGER NOT NULL DEFAULT 1,
  status         TEXT
);
CREATE INDEX IF NOT EXISTS reservations_holding_idx ON reservations(holding_id);
