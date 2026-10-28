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
from app.footage.edit_plan import PLAN_MODES, PlanEditError, apply_plan_edit, plan_signature
from app.footage.runner import (
    CLIP_FILE_GONE,
    PENDING_RELEVANCE,
    enqueue_batch,
    expire_missing_clips,
    insert_keyword,
    insert_segment,
    run_edit_plan,
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
    fresh: bool = False  # skip videos already found -> different results


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


class EditPlanRequest(BaseModel):
    mode: str = "picks"  # 'picks' | 'auto' | 'mixed' -- see edit_plan._segment_candidates


class EditPlanUpdate(BaseModel):
    segments: list[dict]  # [{segment_id, beats: [{type, text, note, clip, added, clip_audio}]}]


class PickRequest(BaseModel):
    segment_id: str
    keyword_id: str | None = None
    video_id: str
    video_title: str = ""
    channel: str = ""
    thumbnail_url: str | None = None
    start: float
    end: float
    label: str = ""
    description: str = ""
    source: str = "suggested"  # 'suggested' (an AI-found moment) | 'custom' (your own timestamps)
    clip_audio: bool = False  # keep the clip's own sound in the edit (otherwise muted under the VO)


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
    plan = db.fetch_one("SELECT * FROM footage_plans WHERE project_id=?", (project_id,))
    out["edit_plan"] = None if not plan else {
        "status": plan["status"],
        "error_message": plan["error_message"],
        "created_at": plan["created_at"],
        "mode": plan["plan_mode"] or "picks",
        # Out of date when what it was built from (pushed clips and/or AI
        # moments, depending on its mode) has changed since.
        "stale": plan["status"] == "done"
        and plan["signature"] != plan_signature(project_id, plan["plan_mode"] or "picks"),
        "plan": json.loads(plan["plan_json"]) if plan["plan_json"] else None,
    }
    out["picks"] = [
        {
            "id": r["id"], "segment_id": r["segment_id"], "keyword_id": r["keyword_id"],
            "video_id": r["video_id"], "video_title": r["video_title"], "channel": r["channel"],
            "thumbnail_url": r["thumbnail_url"], "start": r["start_seconds"], "end": r["end_seconds"],
            "label": r["label"], "description": r["description"], "source": r["source"],
            "clip_audio": bool(r["clip_audio"]),
        }
        for r in db.fetch_all(
            "SELECT * FROM footage_picks WHERE project_id=? ORDER BY created_at, start_seconds", (project_id,),
        )
    ]
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
    for table in ("footage_picks", "footage_plans", "footage_clips", "footage_keywords", "footage_batches", "footage_segments"):
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
    enqueue_batch(project_id, req.keyword_ids, fresh=req.fresh)
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
    if clip["status"] != "done":
        raise HTTPException(404, "clip is not ready")
    if not clip["file_path"] or not Path(clip["file_path"]).exists():
        expire_missing_clips()
        raise HTTPException(410, CLIP_FILE_GONE)
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


@router.post("/projects/{project_id}/edit-plan")
async def create_edit_plan(project_id: str, req: EditPlanRequest | None = None):
    """(Re)builds the script-to-footage edit plan in the background. The
    previous plan stays visible until the new one replaces it."""
    project = db.fetch_one("SELECT mode, status FROM footage_projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "project not found")
    if project["mode"] != "script" or project["status"] != "ready":
        raise HTTPException(409, "An edit plan needs a script project that has finished splitting")
    mode = req.mode if req else "picks"
    if mode not in PLAN_MODES:
        raise HTTPException(400, f"mode must be one of {', '.join(PLAN_MODES)}")
    existing = db.fetch_one("SELECT status FROM footage_plans WHERE project_id=?", (project_id,))
    if existing and existing["status"] == "building":
        return _project_detail(project_id)
    db.execute(
        "INSERT INTO footage_plans (project_id, status, plan_mode) VALUES (?, 'building', ?) "
        "ON CONFLICT(project_id) DO UPDATE SET status='building', plan_mode=excluded.plan_mode, "
        "error_message=NULL, completed_at=NULL",
        (project_id, mode),
    )
    asyncio.create_task(run_edit_plan(project_id, mode))
    return _project_detail(project_id)


def _set_plan_clip_audio(project_id: str, pick_id: str, clip_audio: bool) -> None:
    """Carries a changed sound choice over to every plan beat using that pick."""
    plan = db.fetch_one("SELECT plan_json FROM footage_plans WHERE project_id=? AND status='done'", (project_id,))
    if not plan or not plan["plan_json"]:
        return
    data = json.loads(plan["plan_json"])
    changed = False
    for seg in data.get("segments", []):
        for beat in seg.get("beats", []):
            if (beat.get("clip") or {}).get("pick_id") == pick_id and beat.get("clip_audio") != clip_audio:
                beat["clip_audio"] = beat["clip"]["clip_audio"] = clip_audio
                changed = True
    if changed:
        db.execute("UPDATE footage_plans SET plan_json=? WHERE project_id=?", (json.dumps(data), project_id))


@router.post("/projects/{project_id}/picks")
def push_pick(project_id: str, req: PickRequest):
    """Pushes a clip to the edit plan's shortlist for one segment -- either a
    suggested moment or a range you typed in yourself. Pushing the exact
    same range again only updates its sound choice."""
    if not db.fetch_one(
        "SELECT id FROM footage_segments WHERE id=? AND project_id=?", (req.segment_id, project_id),
    ):
        raise HTTPException(404, "segment not found")
    start = max(0.0, req.start)
    end = req.end
    if end <= start:
        raise HTTPException(400, "The end time must be after the start time")
    if end - start > MAX_CLIP_SECONDS:
        raise HTTPException(400, f"A clip can be at most {MAX_CLIP_SECONDS // 60} minutes long")
    if req.source not in ("suggested", "custom"):
        raise HTTPException(400, "source must be 'suggested' or 'custom'")
    exists = db.fetch_one(
        "SELECT id FROM footage_picks WHERE segment_id=? AND video_id=? AND start_seconds=? AND end_seconds=?",
        (req.segment_id, req.video_id, start, end),
    )
    if exists:
        db.execute("UPDATE footage_picks SET clip_audio=? WHERE id=?", (int(req.clip_audio), exists["id"]))
        _set_plan_clip_audio(project_id, exists["id"], req.clip_audio)
    else:
        db.execute(
            "INSERT INTO footage_picks (id, project_id, segment_id, keyword_id, video_id, video_title, "
            "channel, thumbnail_url, start_seconds, end_seconds, label, description, source, clip_audio) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), project_id, req.segment_id, req.keyword_id, req.video_id,
                req.video_title, req.channel, req.thumbnail_url, start, end,
                req.label.strip(), req.description.strip(), req.source, int(req.clip_audio),
            ),
        )
    return _project_detail(project_id)


@router.delete("/picks/{pick_id}")
def remove_pick(pick_id: str):
    pick = db.fetch_one("SELECT project_id FROM footage_picks WHERE id=?", (pick_id,))
    if not pick:
        raise HTTPException(404, "pick not found")
    db.execute("DELETE FROM footage_picks WHERE id=?", (pick_id,))
    return _project_detail(pick["project_id"])


@router.put("/projects/{project_id}/edit-plan")
def update_edit_plan(project_id: str, req: EditPlanUpdate):
    """Saves hand edits to the plan: removed, moved or swapped clips and
    moved cut points. Only the segments sent are changed."""
    plan = db.fetch_one("SELECT status, plan_json FROM footage_plans WHERE project_id=?", (project_id,))
    if not plan or plan["status"] != "done" or not plan["plan_json"]:
        raise HTTPException(409, "There's no finished plan to edit")
    try:
        updated = apply_plan_edit(json.loads(plan["plan_json"]), req.segments)
    except PlanEditError as e:
        raise HTTPException(400, str(e))
    db.execute(
        "UPDATE footage_plans SET plan_json=? WHERE project_id=?", (json.dumps(updated), project_id),
    )
    return _project_detail(project_id)
