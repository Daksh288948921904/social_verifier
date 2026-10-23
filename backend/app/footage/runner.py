import asyncio
import json
import logging
import uuid

from app.core import db
from app.core.config import settings
from app.footage.matcher import match_video
from app.footage.script_parse import parse_script
from app.footage.search import search_videos
from app.footage.transcript import get_transcript

logger = logging.getLogger(__name__)

PENDING_RELEVANCE = -1  # footage_videos.relevance while a video is still being analysed

# Projects with a worker currently draining their queue. Everything here runs
# on the one event loop, so a plain set is safe.
_active_projects: set[str] = set()


def insert_segment(project_id: str, position: int, title: str, summary: str = "",
                   visual_needs: str = "", script_excerpt: str = "") -> str:
    segment_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO footage_segments (id, project_id, position, title, summary, visual_needs, script_excerpt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (segment_id, project_id, position, title, summary, visual_needs, script_excerpt),
    )
    return segment_id


def insert_keyword(project_id: str, segment_id: str, text: str, rationale: str = "") -> str:
    row = db.fetch_one(
        "SELECT COALESCE(MAX(position), -1) AS last FROM footage_keywords WHERE segment_id=?",
        (segment_id,),
    )
    keyword_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO footage_keywords (id, project_id, segment_id, position, text, rationale) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (keyword_id, project_id, segment_id, row["last"] + 1, text, rationale),
    )
    return keyword_id


async def run_script_parse(project_id: str, script: str) -> None:
    try:
        parsed = await asyncio.to_thread(parse_script, script)
        project = db.fetch_one("SELECT title FROM footage_projects WHERE id=?", (project_id,))
        if project and not project["title"].strip():
            db.execute("UPDATE footage_projects SET title=? WHERE id=?", (parsed.title, project_id))
        for position, seg in enumerate(parsed.segments):
            segment_id = insert_segment(
                project_id, position, seg.title, seg.summary, seg.visual_needs, seg.script_excerpt,
            )
            for kw in seg.keywords:
                insert_keyword(project_id, segment_id, kw["text"], kw["rationale"])
        db.execute("UPDATE footage_projects SET status='ready' WHERE id=?", (project_id,))
    except Exception as e:
        logger.exception("Script parse failed for footage project %s", project_id)
        db.execute(
            "UPDATE footage_projects SET status='error', error_message=? WHERE id=?",
            (str(e), project_id),
        )


def enqueue_batch(project_id: str, keyword_ids: list[str]) -> str:
    """Queues keywords as one batch and makes sure the project's worker is
    running. Re-running a keyword replaces its earlier results. Keywords
    already in flight are left alone rather than queued twice."""
    batch_id = str(uuid.uuid4())
    db.execute("INSERT INTO footage_batches (id, project_id) VALUES (?, ?)", (batch_id, project_id))
    for keyword_id in keyword_ids:
        row = db.fetch_one(
            "SELECT status FROM footage_keywords WHERE id=? AND project_id=?", (keyword_id, project_id),
        )
        if not row or row["status"] in ("queued", "searching", "analyzing"):
            continue
        db.execute("DELETE FROM footage_videos WHERE keyword_id=?", (keyword_id,))
        db.execute(
            "UPDATE footage_keywords SET status='queued', progress='Waiting for its wave…', "
            "error_message=NULL, batch_id=?, queued_at=datetime('now'), completed_at=NULL WHERE id=?",
            (batch_id, keyword_id),
        )
    _finish_batches(project_id)  # a batch whose every keyword was skipped is done immediately
    if project_id not in _active_projects:
        _active_projects.add(project_id)
        asyncio.create_task(_drain_queue(project_id))
    return batch_id


async def _drain_queue(project_id: str) -> None:
    """Works through the project's queued keywords a wave at a time:
    footage_keywords_per_wave keywords side by side, and the next wave only
    once the whole current one has finished. Picks up anything queued while
    it runs, so a second batch started mid-run simply joins the queue."""
    try:
        while True:
            wave = db.fetch_all(
                "SELECT k.id FROM footage_keywords k JOIN footage_segments s ON s.id = k.segment_id "
                "WHERE k.project_id=? AND k.status='queued' "
                "ORDER BY k.queued_at, s.position, k.position LIMIT ?",
                (project_id, max(1, settings.footage_keywords_per_wave)),
            )
            if not wave:
                break
            await asyncio.gather(*(_process_keyword(r["id"]) for r in wave))
            _finish_batches(project_id)
    finally:
        _active_projects.discard(project_id)
        _finish_batches(project_id)


def _finish_batches(project_id: str) -> None:
    for batch in db.fetch_all(
        "SELECT id FROM footage_batches WHERE project_id=? AND status='running'", (project_id,),
    ):
        pending = db.fetch_one(
            "SELECT COUNT(*) AS n FROM footage_keywords WHERE batch_id=? "
            "AND status IN ('queued', 'searching', 'analyzing')",
            (batch["id"],),
        )
        if pending["n"] == 0:
            db.execute(
                "UPDATE footage_batches SET status='done', completed_at=datetime('now') WHERE id=?",
                (batch["id"],),
            )


def _set_keyword(keyword_id: str, status: str, progress: str) -> None:
    db.execute(
        "UPDATE footage_keywords SET status=?, progress=? WHERE id=?", (status, progress, keyword_id),
    )


async def _process_keyword(keyword_id: str) -> None:
    try:
        keyword = dict(db.fetch_one("SELECT * FROM footage_keywords WHERE id=?", (keyword_id,)))
        segment = dict(db.fetch_one("SELECT * FROM footage_segments WHERE id=?", (keyword["segment_id"],)))

        _set_keyword(keyword_id, "searching", "Searching YouTube…")
        videos = await search_videos(keyword["text"], settings.footage_videos_per_keyword)
        if not videos:
            db.execute(
                "UPDATE footage_keywords SET status='done', progress='', completed_at=datetime('now') "
                "WHERE id=?",
                (keyword_id,),
            )
            return

        # Saved straight away (relevance pending) so the cards show up in the
        # UI while each one is still being analysed.
        row_ids = []
        for position, v in enumerate(videos):
            row_id = str(uuid.uuid4())
            row_ids.append(row_id)
            db.execute(
                "INSERT INTO footage_videos (id, keyword_id, position, video_id, title, channel, "
                "thumbnail_url, published_at, duration_seconds, relevance) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row_id, keyword_id, position, v["video_id"], v["title"], v["channel"],
                    v["thumbnail_url"], v["published_at"], v["duration_seconds"], PENDING_RELEVANCE,
                ),
            )

        for i, (row_id, video) in enumerate(zip(row_ids, videos)):
            _set_keyword(keyword_id, "analyzing", f"Reading video {i + 1} of {len(videos)}…")
            try:
                transcript = await asyncio.to_thread(get_transcript, video["video_id"])
                _set_keyword(keyword_id, "analyzing", f"Finding moments in video {i + 1} of {len(videos)}…")
                match = await asyncio.to_thread(match_video, segment, keyword, video, transcript)
                db.execute(
                    "UPDATE footage_videos SET relevance=?, verdict=?, moments_json=?, has_transcript=?, "
                    "duration_seconds=COALESCE(?, duration_seconds), "
                    "channel=CASE WHEN channel='' THEN ? ELSE channel END WHERE id=?",
                    (
                        match.relevance, match.verdict, json.dumps(match.moments),
                        1 if transcript.lines else 0, transcript.duration_seconds,
                        transcript.channel, row_id,
                    ),
                )
            except Exception as e:
                # One unreadable video shouldn't sink the rest of the keyword.
                logger.warning("Analysing video %s failed: %s", video["video_id"], e)
                db.execute(
                    "UPDATE footage_videos SET relevance=0, verdict=? WHERE id=?",
                    (f"Couldn't analyse this video: {e}", row_id),
                )

        db.execute(
            "UPDATE footage_keywords SET status='done', progress='', completed_at=datetime('now') WHERE id=?",
            (keyword_id,),
        )
    except Exception as e:
        logger.exception("Footage keyword %s failed", keyword_id)
        db.execute(
            "UPDATE footage_keywords SET status='error', progress='', error_message=?, "
            "completed_at=datetime('now') WHERE id=?",
            (str(e), keyword_id),
        )


def recover_interrupted() -> None:
    """Background jobs live only in this process, so anything mid-flight when
    the server last stopped is orphaned -- mark it as failed so the UI
    doesn't spin forever and the user can simply run it again."""
    db.execute(
        "UPDATE footage_keywords SET status='error', progress='', "
        "error_message='Interrupted by a server restart -- run it again.' "
        "WHERE status IN ('queued', 'searching', 'analyzing')"
    )
    db.execute(
        "UPDATE footage_videos SET relevance=0, verdict='Analysis was interrupted.' WHERE relevance=?",
        (PENDING_RELEVANCE,),
    )
    db.execute(
        "UPDATE footage_batches SET status='done', completed_at=datetime('now') WHERE status='running'"
    )
    db.execute(
        "UPDATE footage_clips SET status='error', "
        "error_message='Interrupted by a server restart -- download it again.' WHERE status='downloading'"
    )
    db.execute(
        "UPDATE footage_projects SET status='error', "
        "error_message='Interrupted by a server restart -- create the project again.' "
        "WHERE status='analyzing'"
    )
