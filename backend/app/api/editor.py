import asyncio
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core import db
from app.editor.instagram_runner import run_instagram_kit
from app.editor.runner import run_compile
from app.editor.timeline import get_timeline, set_timeline
from app.editor.uploads import list_uploads, save_upload
from app.models.schemas import (
    EditorExportResponse,
    EditorUploadResponse,
    InstagramKitResponse,
    TimelineItem,
    TimelineResponse,
)

router = APIRouter(prefix="/api/verify/{check_id}/editor", tags=["editor"])


def _require_check(check_id: str) -> None:
    if not db.fetch_one("SELECT id FROM reel_checks WHERE id=?", (check_id,)):
        raise HTTPException(404, "reel check not found")


@router.get("/timeline", response_model=TimelineResponse)
def get_timeline_route(check_id: str):
    _require_check(check_id)
    return TimelineResponse(check_id=check_id, items=get_timeline(check_id))


@router.put("/timeline", response_model=TimelineResponse)
def put_timeline_route(check_id: str, items: list[TimelineItem]):
    _require_check(check_id)
    set_timeline(check_id, [item.model_dump() for item in items])
    return TimelineResponse(check_id=check_id, items=items)


@router.get("/uploads", response_model=list[EditorUploadResponse])
def list_uploads_route(check_id: str):
    _require_check(check_id)
    return [EditorUploadResponse(check_id=check_id, **u) for u in list_uploads(check_id)]


@router.post("/uploads", response_model=EditorUploadResponse)
async def create_upload_route(check_id: str, file: UploadFile = File(...)):
    _require_check(check_id)
    content = await file.read()
    result = await asyncio.to_thread(save_upload, check_id, file.filename or "upload.mp4", content)
    return EditorUploadResponse(**result)


@router.post("/compile", response_model=EditorExportResponse)
async def compile_route(check_id: str):
    _require_check(check_id)
    items = get_timeline(check_id)
    export_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO editor_exports (id, check_id, status) VALUES (?, ?, 'compiling')",
        (export_id, check_id),
    )
    asyncio.create_task(run_compile(export_id, check_id, items))
    row = db.fetch_one("SELECT * FROM editor_exports WHERE id=?", (export_id,))
    return EditorExportResponse(**dict(row))


@router.get("/exports/{export_id}", response_model=EditorExportResponse)
def get_export_route(check_id: str, export_id: str):
    row = db.fetch_one(
        "SELECT * FROM editor_exports WHERE id=? AND check_id=?", (export_id, check_id)
    )
    if not row:
        raise HTTPException(404, "export not found")
    return EditorExportResponse(**dict(row))


@router.get("/exports/{export_id}/video")
def get_export_video_route(check_id: str, export_id: str):
    row = db.fetch_one(
        "SELECT status, output_path FROM editor_exports WHERE id=? AND check_id=?",
        (export_id, check_id),
    )
    if not row or row["status"] != "done" or not row["output_path"]:
        raise HTTPException(404, "compiled video not ready")
    return FileResponse(row["output_path"], media_type="video/mp4", filename="compiled.mp4")


@router.post("/exports/{export_id}/instagram", response_model=InstagramKitResponse)
async def create_instagram_kit_route(check_id: str, export_id: str):
    export_row = db.fetch_one(
        "SELECT status FROM editor_exports WHERE id=? AND check_id=?", (export_id, check_id)
    )
    if not export_row:
        raise HTTPException(404, "export not found")
    if export_row["status"] != "done":
        raise HTTPException(400, "compile the video before preparing an Instagram post kit")

    kit_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO instagram_kits (id, export_id, check_id, status) VALUES (?, ?, ?, 'generating')",
        (kit_id, export_id, check_id),
    )
    asyncio.create_task(run_instagram_kit(kit_id, check_id))
    row = db.fetch_one("SELECT * FROM instagram_kits WHERE id=?", (kit_id,))
    return InstagramKitResponse(**dict(row))


@router.get("/exports/{export_id}/instagram/{kit_id}", response_model=InstagramKitResponse)
def get_instagram_kit_route(check_id: str, export_id: str, kit_id: str):
    row = db.fetch_one(
        "SELECT * FROM instagram_kits WHERE id=? AND export_id=? AND check_id=?",
        (kit_id, export_id, check_id),
    )
    if not row:
        raise HTTPException(404, "instagram kit not found")
    return InstagramKitResponse(**dict(row))


@router.get("/exports/{export_id}/instagram/{kit_id}/thumbnail")
def get_instagram_thumbnail_route(check_id: str, export_id: str, kit_id: str):
    row = db.fetch_one(
        "SELECT status, thumbnail_path FROM instagram_kits WHERE id=? AND export_id=? AND check_id=?",
        (kit_id, export_id, check_id),
    )
    if not row or row["status"] != "done" or not row["thumbnail_path"]:
        raise HTTPException(404, "thumbnail not ready")
    return FileResponse(row["thumbnail_path"], media_type="image/png", filename="thumbnail.png")
