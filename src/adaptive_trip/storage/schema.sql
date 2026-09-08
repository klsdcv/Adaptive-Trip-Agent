PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS trips (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version >= 0),
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trip_id, fingerprint)
);
