import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings

_lock = threading.Lock()
_conn: Any = None
_is_postgres = bool(settings.database_url)

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

CREATE TABLE IF NOT EXISTS verify_batches (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'processing',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
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
    batch_id TEXT REFERENCES verify_batches(id),
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
# ALTER TABLE against any database created before they were added.
COLUMN_MIGRATIONS = [
    ("reel_checks", "conclusion", "TEXT"),
    ("reel_checks", "batch_id", "TEXT"),
]


# The whole app is written against SQLite's `?` placeholders and its
# `datetime('now')` idiom (in both the schema and ~15 query call sites
# scattered across other modules). Rather than touch every call site to
# support Postgres, every query passes through this translation when
# DATABASE_URL is set -- `?` and `datetime('now')` never appear as literal
# data anywhere in this codebase's SQL, only as placeholders/idiom, so a
# blanket string replace is safe.
def _pg_translate(sql: str) -> str:
    sql = sql.replace("datetime('now')", "now()")
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    sql = sql.replace("BLOB", "BYTEA")
    sql = sql.replace("?", "%s")
    return sql


def _run_migrations_sqlite(conn: sqlite3.Connection) -> None:
    for table, column, coltype in COLUMN_MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def _run_migrations_postgres(conn) -> None:
    with conn.cursor() as cur:
        for table, column, coltype in COLUMN_MIGRATIONS:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                (table,),
            )
            existing = {row["column_name"] for row in cur.fetchall()}
            if column not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def _connect_postgres():
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=False)
    with conn.cursor() as cur:
        cur.execute(_pg_translate(SCHEMA))
    conn.commit()
    _run_migrations_postgres(conn)
    conn.commit()
    return conn


def _connect_sqlite():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db_path = settings.data_dir / "live_cutter.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _run_migrations_sqlite(conn)
    conn.commit()
    return conn


def get_conn():
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = _connect_postgres() if _is_postgres else _connect_sqlite()
    return _conn


def execute(query: str, params: tuple = ()):
    conn = get_conn()
    with _lock:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute(_pg_translate(query), params)
            conn.commit()
            return cur
        cur = conn.execute(query, params)
        conn.commit()
        return cur


def fetch_one(query: str, params: tuple = ()):
    conn = get_conn()
    with _lock:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute(_pg_translate(query), params)
            return cur.fetchone()
        cur = conn.execute(query, params)
        return cur.fetchone()


def fetch_all(query: str, params: tuple = ()):
    conn = get_conn()
    with _lock:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute(_pg_translate(query), params)
            return cur.fetchall()
        cur = conn.execute(query, params)
        return cur.fetchall()
