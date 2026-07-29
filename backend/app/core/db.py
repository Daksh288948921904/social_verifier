import sqlite3
import threading
from pathlib import Path

from app.core.config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'starting',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    video_path TEXT NOT NULL,
    thumbnail_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    absolute_start REAL NOT NULL,
    absolute_end REAL NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clip_embeddings (
    clip_id TEXT PRIMARY KEY REFERENCES clips(id),
    session_id TEXT NOT NULL,
    embedding BLOB NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_newspapers (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clip_articles (
    clip_id TEXT PRIMARY KEY REFERENCES clips(id),
    article TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reel_checks (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'downloading',
    progress TEXT NOT NULL DEFAULT '',
    manuscript TEXT,
    claims_json TEXT,
    conclusion TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS editor_uploads (
    id TEXT PRIMARY KEY,
    check_id TEXT NOT NULL REFERENCES reel_checks(id),
    filename TEXT NOT NULL,
    video_path TEXT NOT NULL,
    duration_seconds REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS editor_timelines (
    check_id TEXT PRIMARY KEY REFERENCES reel_checks(id),
    items_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS editor_exports (
    id TEXT PRIMARY KEY,
    check_id TEXT NOT NULL REFERENCES reel_checks(id),
    status TEXT NOT NULL DEFAULT 'compiling',
    output_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS instagram_kits (
    id TEXT PRIMARY KEY,
    export_id TEXT NOT NULL REFERENCES editor_exports(id),
    check_id TEXT NOT NULL REFERENCES reel_checks(id),
    status TEXT NOT NULL DEFAULT 'generating',
    thumbnail_path TEXT,
    caption TEXT,
    best_time TEXT,
    audio_style TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS debunk_scripts (
    id TEXT PRIMARY KEY,
    check_id TEXT NOT NULL REFERENCES reel_checks(id),
    status TEXT NOT NULL DEFAULT 'generating',
    script_json TEXT,
    pdf_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
"""


# (table, column, type) added after their table's initial release -- CREATE TABLE IF NOT
# EXISTS is a no-op against an already-existing table, so new columns need an explicit
# ALTER TABLE against any database file created before they were added.
COLUMN_MIGRATIONS = [
    ("reel_checks", "conclusion", "TEXT"),
]


def _run_migrations(conn: sqlite3.Connection) -> None:
    for table, column, coltype in COLUMN_MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        db_path = settings.data_dir / "live_cutter.db"
        _conn = sqlite3.connect(db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        with _lock:
            _conn.executescript(SCHEMA)
            _run_migrations(_conn)
            _conn.commit()
    return _conn


def execute(query: str, params: tuple = ()) -> sqlite3.Cursor:
    conn = get_conn()
    with _lock:
        cur = conn.execute(query, params)
        conn.commit()
        return cur


def fetch_one(query: str, params: tuple = ()) -> sqlite3.Row | None:
    conn = get_conn()
    with _lock:
        cur = conn.execute(query, params)
        return cur.fetchone()


def fetch_all(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = get_conn()
    with _lock:
        cur = conn.execute(query, params)
        return cur.fetchall()
