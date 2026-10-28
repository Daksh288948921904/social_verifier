import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Re-entrant: a query that finds the connection dropped reconnects via
# get_conn() while still holding the lock.
_lock = threading.RLock()
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

CREATE TABLE IF NOT EXISTS clip_reels (
    id TEXT PRIMARY KEY,
    clip_id TEXT NOT NULL REFERENCES clips(id),
    status TEXT NOT NULL DEFAULT 'generating',
    hook_text TEXT,
    audio_style TEXT,
    output_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
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

CREATE TABLE IF NOT EXISTS searches (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS search_results (
    id TEXT PRIMARY KEY,
    search_id TEXT NOT NULL REFERENCES searches(id),
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    thumbnail_url TEXT,
    description TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    video_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS footage_projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    mode TEXT NOT NULL,
    script_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ready',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS footage_segments (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES footage_projects(id),
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    visual_needs TEXT NOT NULL DEFAULT '',
    script_excerpt TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS footage_batches (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES footage_projects(id),
    status TEXT NOT NULL DEFAULT 'running',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS footage_keywords (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES footage_projects(id),
    segment_id TEXT NOT NULL REFERENCES footage_segments(id),
    position INTEGER NOT NULL,
    text TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idle',
    progress TEXT NOT NULL DEFAULT '',
    error_message TEXT,
    batch_id TEXT,
    queued_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS footage_videos (
    id TEXT PRIMARY KEY,
    keyword_id TEXT NOT NULL REFERENCES footage_keywords(id),
    position INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT,
    published_at TEXT,
    duration_seconds REAL,
    has_transcript INTEGER NOT NULL DEFAULT 0,
    relevance INTEGER NOT NULL DEFAULT 0,
    verdict TEXT NOT NULL DEFAULT '',
    moments_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS footage_clips (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES footage_projects(id),
    video_id TEXT NOT NULL,
    video_title TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'downloading',
    file_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS footage_picks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES footage_projects(id),
    segment_id TEXT NOT NULL REFERENCES footage_segments(id),
    keyword_id TEXT,
    video_id TEXT NOT NULL,
    video_title TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'suggested',
    clip_audio INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS footage_plans (
    project_id TEXT PRIMARY KEY REFERENCES footage_projects(id),
    status TEXT NOT NULL DEFAULT 'building',
    plan_json TEXT,
    moment_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS footage_transcripts (
    video_id TEXT PRIMARY KEY,
    duration_seconds REAL,
    channel TEXT NOT NULL DEFAULT '',
    chapters_json TEXT NOT NULL DEFAULT '[]',
    lines_json TEXT NOT NULL DEFAULT '[]',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# (table, column, type) added after their table's initial release -- CREATE TABLE IF NOT
# EXISTS is a no-op against an already-existing table, so new columns need an explicit
# ALTER TABLE against any database created before they were added.
COLUMN_MIGRATIONS = [
    ("reel_checks", "conclusion", "TEXT"),
    ("reel_checks", "batch_id", "TEXT"),
    ("footage_plans", "pick_signature", "TEXT"),
    ("footage_plans", "plan_mode", "TEXT"),
    ("footage_plans", "signature", "TEXT"),
    ("footage_keywords", "exclude_video_ids", "TEXT"),
    ("footage_picks", "clip_audio", "INTEGER NOT NULL DEFAULT 0"),
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

    # autocommit: every call below is its own statement anyway, and it keeps
    # the session from sitting "idle in transaction" between requests, which
    # hosted poolers (Supabase/Supavisor, PgBouncer) cut off.
    # prepare_threshold=None: transaction-mode poolers (Supabase port 6543)
    # can't hold server-side prepared statements across transactions.
    conn = psycopg.connect(
        settings.database_url, row_factory=dict_row, autocommit=True,
        prepare_threshold=None, connect_timeout=15,
    )
    global _schema_ready
    if not _schema_ready:
        with conn.cursor() as cur:
            cur.execute(_pg_translate(SCHEMA))
        _run_migrations_postgres(conn)
        _schema_ready = True
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


_schema_ready = False


def _pg_query(query: str, params: tuple, fetch: str | None):
    """Runs one Postgres statement, reconnecting once if the server or a
    pooler dropped the connection (idle timeouts, database restarts) --
    otherwise one dropped connection would fail every request until the
    app restarted. Caller holds _lock."""
    import psycopg

    global _conn
    for attempt in (1, 2):
        try:
            cur = get_conn().cursor()
            cur.execute(_pg_translate(query), params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return cur
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if attempt == 2:
                raise
            logger.warning("Postgres connection lost; reconnecting")
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


def get_conn():
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = _connect_postgres() if _is_postgres else _connect_sqlite()
    return _conn


def execute(query: str, params: tuple = ()):
    if _is_postgres:
        with _lock:
            return _pg_query(query, params, None)
    conn = get_conn()
    with _lock:
        cur = conn.execute(query, params)
        conn.commit()
        return cur


def fetch_one(query: str, params: tuple = ()):
    if _is_postgres:
        with _lock:
            return _pg_query(query, params, "one")
    conn = get_conn()
    with _lock:
        cur = conn.execute(query, params)
        return cur.fetchone()


def fetch_all(query: str, params: tuple = ()):
    if _is_postgres:
        with _lock:
            return _pg_query(query, params, "all")
    conn = get_conn()
    with _lock:
        cur = conn.execute(query, params)
        return cur.fetchall()
