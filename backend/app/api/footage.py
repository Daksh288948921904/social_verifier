import asyncio
import io
import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pypdf import PdfReader
from starlette.background import BackgroundTask

from app.core import db
from app.core.config import settings
from app.footage.clips import MAX_CLIP_SECONDS, clip_filename, run_clip_download
from app.footage.runner import (
    PENDING_RELEVANCE,
    enqueue_batch,
    insert_keyword,
    insert_segment,
    run_script_parse,
)

router = APIRouter(prefix="/api/footage", tags=["footage"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
RUNNING_STATUSES = ("queued", "searching", "analyzing")


class CreateProjectRequest(BaseModel):
    mode: str  # 'script' | 'keywords'
    title: str = ""
    script: str = ""
    keywords: list[str] = []


class CreateBatchRequest(BaseModel):
    keyword_ids: list[str]


class AddKeywordRequest(BaseModel):
    text: str


class ClipRequest(BaseModel):
    video_id: str
    video_title: str = ""
    segment_position: int = 0
    label: str = ""
    start: float
    end: float


class CreateClipsRequest(BaseModel):
    clips: list[ClipRequest]


def _create_script_project(title: str, script: str) -> dict:
    if len(script.strip()) < 40:
        raise HTTPException(400, "The script is too short to split into segments")
    project_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO footage_projects (id, title, mode, script_text, status) "
        "VALUES (?, ?, 'script', ?, 'analyzing')",
        (project_id, title.strip(), script),
    )
    asyncio.create_task(run_script_parse(project_id, script))
    return _project_detail(project_id)


@router.post("/projects")
async def create_project(req: CreateProjectRequest):
    if req.mode == "script":
        return _create_script_project(req.title, req.script)
    if req.mode != "keywords":
        raise HTTPException(400, "mode must be 'script' or 'keywords'")

    keywords = list(dict.fromkeys(k.strip() for k in req.keywords if k.strip()))
    if not keywords:
        raise HTTPException(400, "Add at least one keyword")
    project_id = str(uuid.uuid4())
    title = req.title.strip() or ", ".join(keywords[:3]) + ("…" if len(keywords) > 3 else "")
    db.execute(
        "INSERT INTO footage_projects (id, title, mode, status) VALUES (?, ?, 'keywords', 'ready')",
        (project_id, title),
    )
    segment_id = insert_segment(project_id, 0, "Keywords")
    for k in keywords:
        insert_keyword(project_id, segment_id, k)
    return _project_detail(project_id)


@router.post("/projects/upload")
async def create_project_from_file(file: UploadFile = File(...), title: str = Form("")):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File is larger than 10 MB")
    name = (file.filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        try:
            reader = PdfReader(io.BytesIO(data))
            script = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise HTTPException(400, f"Couldn't read that PDF: {e}")
    else:
        script = data.decode("utf-8", errors="replace")
    if not script.strip():
        raise HTTPException(400, "No text found in that file (a scanned PDF has no text layer)")
    default_title = (file.filename or "").rsplit(".", 1)[0]
    return _create_script_project(title or default_title, script)


@router.get("/projects")
def list_projects():
    rows = db.fetch_all(
        "SELECT p.id, p.title, p.mode, p.status, p.created_at, "
        "(SELECT COUNT(*) FROM footage_segments s WHERE s.project_id = p.id) AS segment_count, "
        "(SELECT COUNT(*) FROM footage_keywords k WHERE k.project_id = p.id) AS keyword_count, "
        "(SELECT COUNT(*) FROM footage_keywords k WHERE k.project_id = p.id AND k.status = 'done') "
        "AS done_keyword_count, "
        "(SELECT COUNT(*) FROM footage_videos v JOIN footage_keywords k ON k.id = v.keyword_id "
        "WHERE k.project_id = p.id) AS video_count "
        "FROM footage_projects p ORDER BY p.created_at DESC"
    )
    return [dict(r) for r in rows]


def _project_detail(project_id: str) -> dict:
    project = db.fetch_one("SELECT * FROM footage_projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "project not found")
    segments = [dict(r) for r in db.fetch_all(
        "SELECT id, position, title, summary, visual_needs, script_excerpt FROM footage_segments "
        "WHERE project_id=? ORDER BY position",
        (project_id,),
    )]
    keywords = [dict(r) for r in db.fetch_all(
        "SELECT id, segment_id, position, text, rationale, status, progress, error_message, batch_id, "
        "completed_at FROM footage_keywords WHERE project_id=? ORDER BY position",
        (project_id,),
    )]
    videos = db.fetch_all(
        "SELECT v.* FROM footage_videos v JOIN footage_keywords k ON k.id = v.keyword_id "
        "WHERE k.project_id=? ORDER BY v.position",
        (project_id,),
    )

    videos_by_keyword: dict[str, list[dict]] = {}
    for v in videos:
        d = dict(v)
        pending = d["relevance"] == PENDING_RELEVANCE
        videos_by_keyword.setdefault(d["keyword_id"], []).append({
            "id": d["id"],
            "video_id": d["video_id"],
            "title": d["title"],
            "channel": d["channel"],
            "thumbnail_url": d["thumbnail_url"],
            "published_at": d["published_at"],
            "duration_seconds": d["duration_seconds"],
            "has_transcript": bool(d["has_transcript"]),
            "analyzed": not pending,
            "relevance": None if pending else d["relevance"],
            "verdict": d["verdict"],
            "moments": json.loads(d["moments_json"] or "[]"),
        })
    keywords_by_segment: dict[str, list[dict]] = {}
    for k in keywords:
        k["videos"] = videos_by_keyword.get(k["id"], [])
        keywords_by_segment.setdefault(k.pop("segment_id"), []).append(k)
    for s in segments:
        s["keywords"] = keywords_by_segment.get(s["id"], [])

    batches = []
    for b in db.fetch_all(
        "SELECT * FROM footage_batches WHERE project_id=? ORDER BY created_at DESC LIMIT 10", (project_id,),
    ):
        b = dict(b)
        mine = [k for k in keywords if k["batch_id"] == b["id"]]
        b["total"] = len(mine)
        b["finished"] = sum(1 for k in mine if k["status"] not in RUNNING_STATUSES)
        batches.append(b)

    out = dict(project)
    out.pop("script_text", None)
    out["segments"] = segments
    out["batches"] = batches
    out["keywords_per_wave"] = settings.footage_keywords_per_wave
    out["clips"] = [
        {k: c[k] for k in (
            "id", "video_id", "video_title", "filename", "label", "start_seconds", "end_seconds",
            "status", "error_message", "created_at",
        )}
        for c in db.fetch_all(
            "SELECT * FROM footage_clips WHERE project_id=? ORDER BY filename", (project_id,),
        )
    ]
    return out


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    return _project_detail(project_id)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    if not db.fetch_one("SELECT id FROM footage_projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "project not found")
    running = db.fetch_one(
        "SELECT COUNT(*) AS n FROM footage_keywords WHERE project_id=? AND status IN (?, ?, ?)",
        (project_id, *RUNNING_STATUSES),
    )
    if running["n"]:
        raise HTTPException(409, "Wait for the running batch to finish before deleting this project")
    db.execute(
        "DELETE FROM footage_videos WHERE keyword_id IN (SELECT id FROM footage_keywords WHERE project_id=?)",
        (project_id,),
    )
    downloading = db.fetch_one(
        "SELECT COUNT(*) AS n FROM footage_clips WHERE project_id=? AND status='downloading'", (project_id,),
    )
    if downloading["n"]:
        raise HTTPException(409, "Wait for the clip downloads to finish before deleting this project")
    shutil.rmtree(settings.data_dir / "footage_clips" / project_id, ignore_errors=True)
    for table in ("footage_clips", "footage_keywords", "footage_batches", "footage_segments"):
        db.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
    db.execute("DELETE FROM footage_projects WHERE id=?", (project_id,))
    return {"ok": True}


@router.post("/projects/{project_id}/batches")
async def create_batch(project_id: str, req: CreateBatchRequest):
    project = db.fetch_one("SELECT status FROM footage_projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "project not found")
    if project["status"] != "ready":
        raise HTTPException(409, "The script is still being split into segments")
    if not req.keyword_ids:
        raise HTTPException(400, "Select at least one keyword")
    enqueue_batch(project_id, req.keyword_ids)
    return _project_detail(project_id)


@router.post("/projects/{project_id}/segments/{segment_id}/keywords")
def add_keyword(project_id: str, segment_id: str, req: AddKeywordRequest):
    if not db.fetch_one(
        "SELECT id FROM footage_segments WHERE id=? AND project_id=?", (segment_id, project_id),
    ):
        raise HTTPException(404, "segment not found")
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Keyword is empty")
    insert_keyword(project_id, segment_id, text)
    return _project_detail(project_id)


@router.delete("/keywords/{keyword_id}")
def delete_keyword(keyword_id: str):
    keyword = db.fetch_one("SELECT project_id, status FROM footage_keywords WHERE id=?", (keyword_id,))
    if not keyword:
        raise HTTPException(404, "keyword not found")
    if keyword["status"] in RUNNING_STATUSES:
        raise HTTPException(409, "This keyword is still running")
    db.execute("DELETE FROM footage_videos WHERE keyword_id=?", (keyword_id,))
    db.execute("DELETE FROM footage_keywords WHERE id=?", (keyword_id,))
    return _project_detail(keyword["project_id"])


@router.post("/projects/{project_id}/clips")
async def create_clips(project_id: str, req: CreateClipsRequest):
    """Queues one or more moments for download. Asking for a moment that's
    already downloaded (or downloading) is a no-op, so "download best picks"
    can be pressed again safely; a failed one is retried."""
    if not db.fetch_one("SELECT id FROM footage_projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "project not found")
    for c in req.clips:
        start = max(0.0, c.start)
        end = min(c.end, start + MAX_CLIP_SECONDS)
        if end <= start:
            raise HTTPException(400, f"Invalid time range {c.start}-{c.end}")
        existing = db.fetch_one(
            "SELECT id, status FROM footage_clips WHERE project_id=? AND video_id=? "
            "AND start_seconds=? AND end_seconds=?",
            (project_id, c.video_id, start, end),
        )
        if existing and existing["status"] != "error":
            continue
        if existing:
            clip_id = existing["id"]
            db.execute(
                "UPDATE footage_clips SET status='downloading', error_message=NULL, completed_at=NULL "
                "WHERE id=?",
                (clip_id,),
            )
        else:
            clip_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO footage_clips (id, project_id, video_id, video_title, filename, label, "
                "start_seconds, end_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    clip_id, project_id, c.video_id, c.video_title,
                    clip_filename(c.segment_position, c.label or c.video_title, start),
                    c.label, start, end,
                ),
            )
        asyncio.create_task(run_clip_download(clip_id))
    return _project_detail(project_id)


def _ready_clip(clip_id: str):
    clip = db.fetch_one("SELECT * FROM footage_clips WHERE id=?", (clip_id,))
    if not clip:
        raise HTTPException(404, "clip not found")
    if clip["status"] != "done" or not clip["file_path"] or not Path(clip["file_path"]).exists():
        raise HTTPException(404, "clip is not ready")
    return clip


@router.get("/clips/{clip_id}/file")
def get_clip_file(clip_id: str, download: bool = True):
    clip = _ready_clip(clip_id)
    return FileResponse(
        clip["file_path"], media_type="video/mp4",
        filename=clip["filename"] if download else None,
    )


@router.get("/projects/{project_id}/clips.zip")
def download_all_clips(project_id: str):
    project = db.fetch_one("SELECT title FROM footage_projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "project not found")
    clips = [
        c for c in db.fetch_all(
            "SELECT * FROM footage_clips WHERE project_id=? AND status='done' ORDER BY filename", (project_id,),
        )
        if c["file_path"] and Path(c["file_path"]).exists()
    ]
    if not clips:
        raise HTTPException(404, "No downloaded clips yet")

    # MP4s are already compressed -- ZIP_STORED just bundles them, which is
    # far quicker than deflating video for no size gain.
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    used: set[str] = set()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
        for c in clips:
            name = c["filename"]
            n = 2
            while name in used:  # two moments can share a label and start second
                name = c["filename"].replace(".mp4", f"_{n}.mp4")
                n += 1
            used.add(name)
            zf.write(c["file_path"], name)
    tmp.close()
    zip_name = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in project["title"]).strip() or "clips"
    return FileResponse(
        tmp.name, media_type="application/zip", filename=f"{zip_name} clips.zip",
        background=BackgroundTask(Path(tmp.name).unlink, missing_ok=True),
    )


@router.delete("/clips/{clip_id}")
def delete_clip(clip_id: str):
    clip = db.fetch_one("SELECT project_id, status, file_path FROM footage_clips WHERE id=?", (clip_id,))
    if not clip:
        raise HTTPException(404, "clip not found")
    if clip["status"] == "downloading":
        raise HTTPException(409, "This clip is still downloading")
    if clip["file_path"]:
        Path(clip["file_path"]).unlink(missing_ok=True)
    db.execute("DELETE FROM footage_clips WHERE id=?", (clip_id,))
    return _project_detail(clip["project_id"])
