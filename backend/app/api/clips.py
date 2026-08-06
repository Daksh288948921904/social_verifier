import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.clipping.cutter import cut_clip
from app.clipping.reel_runner import run_reel_export
from app.clipping.thumbnail import generate_thumbnail
from app.core import db
from app.models.schemas import (
    ClipReelResponse,
    ClipResponse,
    FullArticleResponse,
    RenameClipRequest,
    RetrimClipRequest,
)
from app.rag.newspaper import generate_full_article
from app.session_runner import active_sessions

router = APIRouter(prefix="/api", tags=["clips"])


def _row_to_clip(row) -> ClipResponse:
    d = dict(row)
    return ClipResponse(**{k: d[k] for k in ClipResponse.model_fields})


@router.get("/sessions/{session_id}/clips", response_model=list[ClipResponse])
def list_clips(session_id: str):
    rows = db.fetch_all(
        "SELECT * FROM clips WHERE session_id=? AND status!='deleted' ORDER BY start_seconds",
        (session_id,),
    )
    return [_row_to_clip(r) for r in rows]


def _get_clip_row(clip_id: str):
    row = db.fetch_one("SELECT * FROM clips WHERE id=?", (clip_id,))
    if not row:
        raise HTTPException(404, "clip not found")
    return row


@router.patch("/clips/{clip_id}", response_model=ClipResponse)
def rename_clip(clip_id: str, req: RenameClipRequest):
    row = _get_clip_row(clip_id)
    title = req.title if req.title is not None else row["title"]
    summary = req.summary if req.summary is not None else row["summary"]
    db.execute("UPDATE clips SET title=?, summary=? WHERE id=?", (title, summary, clip_id))
    return _row_to_clip(_get_clip_row(clip_id))


@router.post("/clips/{clip_id}/retrim", response_model=ClipResponse)
def retrim_clip(clip_id: str, req: RetrimClipRequest):
    row = _get_clip_row(clip_id)
    runner = active_sessions.get(row["session_id"])
    if not runner:
        raise HTTPException(400, "session is no longer active; cannot re-trim")

    video_path = Path(row["video_path"])
    thumb_path = Path(row["thumbnail_path"])
    cut_clip(
        runner.session_dir / "segments", runner.capture.index,
        req.start_seconds, req.end_seconds, video_path,
    )
    generate_thumbnail(video_path, thumb_path)
    db.execute(
        "UPDATE clips SET start_seconds=?, end_seconds=? WHERE id=?",
        (req.start_seconds, req.end_seconds, clip_id),
    )
    return _row_to_clip(_get_clip_row(clip_id))


@router.delete("/clips/{clip_id}")
def delete_clip(clip_id: str):
    _get_clip_row(clip_id)
    db.execute("UPDATE clips SET status='deleted' WHERE id=?", (clip_id,))
    return {"ok": True}


@router.get("/clips/{clip_id}/video")
def get_clip_video(clip_id: str):
    row = _get_clip_row(clip_id)
    path = Path(row["video_path"])
    if not path.exists():
        raise HTTPException(404, "video file missing")
    return FileResponse(path, media_type="video/mp4")


@router.get("/clips/{clip_id}/thumbnail")
def get_clip_thumbnail(clip_id: str):
    row = _get_clip_row(clip_id)
    path = Path(row["thumbnail_path"])
    if not path.exists():
        raise HTTPException(404, "thumbnail file missing")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/clips/{clip_id}/full-article", response_model=FullArticleResponse)
def get_full_article(clip_id: str):
    _get_clip_row(clip_id)
    article = generate_full_article(clip_id)
    return FullArticleResponse(clip_id=clip_id, article=article)


def _row_to_reel(row) -> ClipReelResponse:
    d = dict(row)
    return ClipReelResponse(
        id=d["id"], clip_id=d["clip_id"], status=d["status"],
        hook_text=d["hook_text"], audio_style=d["audio_style"],
        error_message=d["error_message"],
        created_at=d["created_at"], completed_at=d["completed_at"],
    )


@router.post("/clips/{clip_id}/reel", response_model=ClipReelResponse)
async def create_clip_reel(clip_id: str):
    _get_clip_row(clip_id)
    reel_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO clip_reels (id, clip_id, status) VALUES (?, ?, 'generating')",
        (reel_id, clip_id),
    )
    asyncio.create_task(run_reel_export(reel_id, clip_id))
    row = db.fetch_one("SELECT * FROM clip_reels WHERE id=?", (reel_id,))
    return _row_to_reel(row)


@router.get("/clips/{clip_id}/reel/{reel_id}", response_model=ClipReelResponse)
def get_clip_reel(clip_id: str, reel_id: str):
    row = db.fetch_one("SELECT * FROM clip_reels WHERE id=? AND clip_id=?", (reel_id, clip_id))
    if not row:
        raise HTTPException(404, "reel not found")
    return _row_to_reel(row)


@router.get("/clips/{clip_id}/reel/{reel_id}/video")
def get_clip_reel_video(clip_id: str, reel_id: str):
    row = db.fetch_one("SELECT * FROM clip_reels WHERE id=? AND clip_id=?", (reel_id, clip_id))
    if not row or row["status"] != "done" or not row["output_path"]:
        raise HTTPException(404, "reel not ready")
    return FileResponse(row["output_path"], media_type="video/mp4", filename="reel.mp4")
