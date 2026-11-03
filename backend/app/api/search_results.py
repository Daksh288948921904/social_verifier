import asyncio
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from pydantic import BaseModel

from app.core import db
import uuid

from app.footage.clips import MAX_CLIP_SECONDS
from app.search.runner import run_fetch, run_range_clip, run_smart_clip
from app.search.smart_clip import MAX_SECONDS, MIN_SECONDS

router = APIRouter(prefix="/api/search-results", tags=["search-results"])


def _get_result(result_id: str):
    row = db.fetch_one("SELECT * FROM search_results WHERE id=?", (result_id,))
    if not row:
        raise HTTPException(404, "result not found")
    return row


def _detail(result_id: str) -> dict:
    out = dict(_get_result(result_id))
    out["ranges"] = [
        {
            "id": c["id"], "start": c["start_seconds"], "end": c["end_seconds"],
            "status": c["status"], "error_message": c["error_message"],
        }
        for c in db.fetch_all(
            "SELECT * FROM search_range_clips WHERE result_id=? ORDER BY created_at", (result_id,),
        )
    ]
    return out


def _safe_title(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', " ", title).strip()[:60] or "clip"


def _mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


@router.get("/{result_id}")
def get_result(result_id: str):
    return _detail(result_id)


@router.post("/{result_id}/fetch")
async def fetch_result(result_id: str):
    row = _get_result(result_id)
    if row["status"] != "fetching":
        db.execute(
            "UPDATE search_results SET status='fetching', error_message=? WHERE id=?",
            (None, result_id),
        )
        asyncio.create_task(run_fetch(result_id))
    return _detail(result_id)


class SmartClipRequest(BaseModel):
    seconds: float = MAX_SECONDS


@router.post("/{result_id}/smart")
async def smart_clip(result_id: str, req: SmartClipRequest | None = None):
    """Finds a clean 8-10s stretch (no ticker, logo or on-screen text) of a
    YouTube result that fits the search, and cuts just that part."""
    row = _get_result(result_id)
    if row["source"] != "youtube":
        raise HTTPException(400, "Smart clips work on YouTube results only")
    seconds = max(MIN_SECONDS, min(MAX_SECONDS, (req or SmartClipRequest()).seconds))
    if row["smart_status"] != "analyzing":
        db.execute(
            "UPDATE search_results SET smart_status='analyzing', smart_note='Queued…', "
            "smart_start=NULL, smart_end=NULL, smart_path=NULL WHERE id=?",
            (result_id,),
        )
        asyncio.create_task(run_smart_clip(result_id, seconds))
    return _detail(result_id)


def _without_audio(path: Path) -> Path:
    """A copy of the clip with the sound track dropped -- a stream copy, so
    it takes a moment and leaves the picture untouched. Made once, then reused."""
    muted = path.with_name(f"{path.stem}_noaudio.mp4")
    if not muted.exists():
        tmp = muted.with_suffix(".tmp.mp4")
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-map", "0:v", "-c", "copy", "-an", str(tmp)],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise HTTPException(500, f"Couldn't remove the audio: {r.stderr.strip()[-200:]}")
        tmp.replace(muted)
    return muted


@router.get("/{result_id}/smart-video")
def get_smart_video(result_id: str, download: bool = False, audio: bool = True):
    row = _get_result(result_id)
    path = Path(row["smart_path"]) if row["smart_path"] else None
    if row["smart_status"] != "done" or not path or not path.exists():
        raise HTTPException(404, "smart clip not ready")
    if not audio:
        path = _without_audio(path)
    suffix = "" if audio else " (no audio)"
    name = f"{_safe_title(row['title'])} {_mmss(row['smart_start'] or 0)}{suffix}.mp4" if download else None
    return FileResponse(path, media_type="video/mp4", filename=name)


class RangeRequest(BaseModel):
    start: float
    end: float


@router.post("/{result_id}/ranges")
async def cut_range(result_id: str, req: RangeRequest):
    """Cuts your own [start, end] out of a search result. Asking for the same
    range again reuses the clip unless the last attempt failed."""
    _get_result(result_id)
    start, end = round(max(0.0, req.start), 1), round(req.end, 1)
    if end <= start:
        raise HTTPException(400, "The end time must be after the start time")
    if end - start > MAX_CLIP_SECONDS:
        raise HTTPException(400, f"A clip can be at most {MAX_CLIP_SECONDS // 60} minutes long")
    existing = db.fetch_one(
        "SELECT id, status FROM search_range_clips WHERE result_id=? AND start_seconds=? AND end_seconds=?",
        (result_id, start, end),
    )
    if existing and existing["status"] != "error":
        return _detail(result_id)
    if existing:
        clip_id = existing["id"]
        db.execute("UPDATE search_range_clips SET status='cutting', error_message=NULL WHERE id=?", (clip_id,))
    else:
        clip_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO search_range_clips (id, result_id, start_seconds, end_seconds) VALUES (?, ?, ?, ?)",
            (clip_id, result_id, start, end),
        )
    asyncio.create_task(run_range_clip(clip_id))
    return _detail(result_id)


@router.get("/ranges/{clip_id}/file")
def get_range_file(clip_id: str, audio: bool = True):
    clip = db.fetch_one(
        "SELECT c.*, r.title FROM search_range_clips c JOIN search_results r ON r.id = c.result_id WHERE c.id=?",
        (clip_id,),
    )
    path = Path(clip["file_path"]) if clip and clip["file_path"] else None
    if not clip or clip["status"] != "done" or not path or not path.exists():
        raise HTTPException(404, "clip not ready")
    if not audio:
        path = _without_audio(path)
    name = f"{_safe_title(clip['title'])} {_mmss(clip['start_seconds'])}-{_mmss(clip['end_seconds'])}"
    return FileResponse(path, media_type="video/mp4", filename=f"{name}{'' if audio else ' (no audio)'}.mp4")


@router.delete("/ranges/{clip_id}")
def delete_range(clip_id: str):
    clip = db.fetch_one("SELECT result_id, status, file_path FROM search_range_clips WHERE id=?", (clip_id,))
    if not clip:
        raise HTTPException(404, "clip not found")
    if clip["status"] == "cutting":
        raise HTTPException(409, "This clip is still being cut")
    if clip["file_path"]:
        path = Path(clip["file_path"])
        path.unlink(missing_ok=True)
        path.with_name(f"{path.stem}_noaudio.mp4").unlink(missing_ok=True)
    db.execute("DELETE FROM search_range_clips WHERE id=?", (clip_id,))
    return _detail(clip["result_id"])


@router.get("/{result_id}/video")
def get_result_video(result_id: str):
    row = _get_result(result_id)
    if not row["video_path"]:
        raise HTTPException(404, "video not ready")
    path = Path(row["video_path"])
    if not path.exists():
        raise HTTPException(404, "video file missing")
    return FileResponse(path, media_type="video/mp4")
