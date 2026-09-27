"""SQLite schema and connection helper."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id                  INTEGER PRIMARY KEY,
    title               TEXT NOT NULL,
    url                 TEXT NOT NULL,
    canonical_url       TEXT NOT NULL UNIQUE,
    source              TEXT NOT NULL,
    published_at        TEXT NOT NULL,              -- ISO-8601 UTC, e.g. 2026-09-25T14:02:00Z
    published_estimated INTEGER NOT NULL DEFAULT 0, -- 1 when the source gave no date
    fetched_at          TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 300),
    -- derived (recomputed after every ingestion)
    category            TEXT,
    cluster_id          INTEGER,
    aum_usd             REAL
);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_items_cluster ON items(cluster_id);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title, description, content='items', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, description) VALUES (new.id, new.title, new.description);
END;
CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, description) VALUES ('delete', old.id, old.title, old.description);
END;
CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE OF title, description ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, description) VALUES ('delete', old.id, old.title, old.description);
    INSERT INTO items_fts(rowid, title, description) VALUES (new.id, new.title, new.description);
END;

CREATE TABLE IF NOT EXISTS item_firms (
    item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    firm     TEXT NOT NULL,              -- display name
    crd      TEXT,                       -- SEC-verified firms only
    verified INTEGER NOT NULL DEFAULT 0, -- 1 = matched in SEC adviser data, 0 = regex fallback
    in_title INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id, firm)
);

CREATE TABLE IF NOT EXISTS clusters (
    id               INTEGER PRIMARY KEY,   -- = smallest item id in the cluster
    headline_item_id INTEGER NOT NULL,
    headline         TEXT NOT NULL,
    url              TEXT NOT NULL,
    category         TEXT,
    first_seen       TEXT NOT NULL,         -- min fetched_at
    first_published  TEXT NOT NULL,
    last_published   TEXT NOT NULL,
    outlet_count     INTEGER NOT NULL,
    item_count       INTEGER NOT NULL,
    aum_usd          REAL
);
CREATE INDEX IF NOT EXISTS idx_clusters_last ON clusters(last_published);

CREATE TABLE IF NOT EXISTS mna_deals (
    cluster_id     INTEGER PRIMARY KEY,
    acquirer       TEXT NOT NULL DEFAULT '',
    target         TEXT NOT NULL DEFAULT '',
    target_aum_usd REAL,
    deal_type      TEXT NOT NULL DEFAULT '',
    deal_date      TEXT NOT NULL,
    confidence     TEXT NOT NULL CHECK (confidence IN ('high', 'low')),
    note           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS source_status (
    name                TEXT PRIMARY KEY,
    method              TEXT NOT NULL,
    url_used            TEXT NOT NULL DEFAULT '',
    discovered_feed_url TEXT NOT NULL DEFAULT '',
    items_last_run      INTEGER NOT NULL DEFAULT 0,
    new_last_run        INTEGER NOT NULL DEFAULT 0,
    ok                  INTEGER NOT NULL DEFAULT 0,
    reason              TEXT NOT NULL DEFAULT '',
    last_run_at         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS http_cache (
    url           TEXT PRIMARY KEY,
    etag          TEXT,
    last_modified TEXT
);

CREATE TABLE IF NOT EXISTS sec_firms (
    crd           TEXT PRIMARY KEY,
    sec_number    TEXT,
    legal_name    TEXT NOT NULL,
    business_name TEXT NOT NULL,
    city          TEXT,
    state         TEXT,
    aum_usd       REAL,
    data_date     TEXT NOT NULL          -- date of the SEC file this row came from (YYYY-MM-DD)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# Columns added after phase 1: (table, column, DDL). Applied to existing databases on connect.
MIGRATIONS = [
    ("item_firms", "crd", "ALTER TABLE item_firms ADD COLUMN crd TEXT"),
    ("item_firms", "verified", "ALTER TABLE item_firms ADD COLUMN verified INTEGER NOT NULL DEFAULT 0"),
    ("item_firms", "in_title", "ALTER TABLE item_firms ADD COLUMN in_title INTEGER NOT NULL DEFAULT 0"),
    ("mna_deals", "press_release", "ALTER TABLE mna_deals ADD COLUMN press_release INTEGER NOT NULL DEFAULT 0"),
    ("clusters", "sec_aum_usd", "ALTER TABLE clusters ADD COLUMN sec_aum_usd REAL"),
    ("clusters", "sec_aum_crd", "ALTER TABLE clusters ADD COLUMN sec_aum_crd TEXT"),
    ("source_status", "dropped_last_run", "ALTER TABLE source_status ADD COLUMN dropped_last_run INTEGER NOT NULL DEFAULT 0"),
    ("source_status", "kind", "ALTER TABLE source_status ADD COLUMN kind TEXT NOT NULL DEFAULT 'feed'"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, ddl in MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(ddl)
    conn.commit()


def adopt_legacy_db(path: Path) -> bool:
    """One-time rename of a database left under the project's earlier name (data/wealthwire.db → fiduciarywire.db),
    with its WAL/SHM side files, so an existing local install keeps its history."""
    if path.exists():
        return False
    for old in paths.LEGACY_DB_NAMES:
        legacy = path.with_name(old)
        if legacy.exists():
            for suffix in ("", "-wal", "-shm"):
                side = legacy.with_name(legacy.name + suffix)
                if side.exists():
                    side.rename(path.with_name(path.name + suffix))
            return True
    return False


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or paths.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path == paths.db_path():
        adopt_legacy_db(path)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def backup_to(dest: Path) -> None:
    """Consistent copy of the live DB (includes anything still in the WAL), for carrying state forward."""
    src = connect()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    out = sqlite3.connect(dest)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
