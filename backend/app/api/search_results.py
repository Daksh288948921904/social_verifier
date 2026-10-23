import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core import db
from app.search.runner import run_fetch

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


@router.get("/{result_id}/video")
def get_result_video(result_id: str):
    row = _get_result(result_id)
    if not row["video_path"]:
        raise HTTPException(404, "video not ready")
    path = Path(row["video_path"])
    if not path.exists():
        raise HTTPException(404, "video file missing")
    return FileResponse(path, media_type="video/mp4")
