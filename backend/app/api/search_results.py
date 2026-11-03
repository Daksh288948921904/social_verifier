import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from pydantic import BaseModel

from app.core import db
from app.search.runner import run_fetch, run_smart_clip
from app.search.smart_clip import MAX_SECONDS, MIN_SECONDS

router = APIRouter(prefix="/api/search-results", tags=["search-results"])


def _get_result(result_id: str):
    row = db.fetch_one("SELECT * FROM search_results WHERE id=?", (result_id,))
    if not row:
        raise HTTPException(404, "result not found")
    return row


@router.get("/{result_id}")
def get_result(result_id: str):
    return dict(_get_result(result_id))


@router.post("/{result_id}/fetch")
async def fetch_result(result_id: str):
    row = _get_result(result_id)
    if row["status"] != "fetching":
        db.execute(
            "UPDATE search_results SET status='fetching', error_message=? WHERE id=?",
            (None, result_id),
        )
        asyncio.create_task(run_fetch(result_id))
    return dict(_get_result(result_id))


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
    return dict(_get_result(result_id))


@router.get("/{result_id}/smart-video")
def get_smart_video(result_id: str, download: bool = False):
    row = _get_result(result_id)
    path = Path(row["smart_path"]) if row["smart_path"] else None
    if row["smart_status"] != "done" or not path or not path.exists():
        raise HTTPException(404, "smart clip not ready")
    m, s = divmod(int(row["smart_start"] or 0), 60)
    title = re.sub(r'[\\/:*?"<>|]+', " ", row["title"]).strip()[:60] or "clip"
    name = f"{title} {m}m{s:02d}s.mp4" if download else None
    return FileResponse(path, media_type="video/mp4", filename=name)


@router.get("/{result_id}/video")
def get_result_video(result_id: str):
    row = _get_result(result_id)
    if not row["video_path"]:
        raise HTTPException(404, "video not ready")
    path = Path(row["video_path"])
    if not path.exists():
        raise HTTPException(404, "video file missing")
    return FileResponse(path, media_type="video/mp4")
