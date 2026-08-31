// Package store opens the catalog database and applies the embedded schema.
// Connection pool limits and pragmas are set here so that every caller works
// against the same configuration.
package store

import (
	"database/sql"
	_ "embed"

	_ "modernc.org/sqlite"
)

//go:embed schema.sql
var schema string

// Open returns a handle with the schema applied. The caller owns the handle.
func Open(path string) (*sql.DB, error) {
	db, err := sql.Open("sqlite", path+"?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)")
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	if _, err := db.Exec(`PRAGMA foreign_keys = ON`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}
