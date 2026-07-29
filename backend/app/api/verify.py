import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core import db
from app.core.config import settings
from app.models.schemas import CreateReelCheckRequest, DebunkScriptResponse, ReelCheckResponse
from app.verifier.clip_cutter import cut_claim_clip
from app.verifier.debunk_runner import run_debunk_script
from app.verifier.runner import run_reel_check

router = APIRouter(prefix="/api/verify", tags=["verify"])


def _row_to_response(row) -> ReelCheckResponse:
    d = dict(row)
    claims = json.loads(d["claims_json"]) if d["claims_json"] else []
    return ReelCheckResponse(
        id=d["id"], url=d["url"], status=d["status"], progress=d["progress"],
        manuscript=d["manuscript"], claims=claims, conclusion=d["conclusion"],
        error_message=d["error_message"],
        created_at=d["created_at"], completed_at=d["completed_at"],
    )


@router.post("", response_model=ReelCheckResponse)
async def create_reel_check(req: CreateReelCheckRequest):
    check_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO reel_checks (id, url, status) VALUES (?, ?, 'downloading')",
        (check_id, req.url),
    )
    asyncio.create_task(run_reel_check(check_id, req.url))
    row = db.fetch_one("SELECT * FROM reel_checks WHERE id=?", (check_id,))
    return _row_to_response(row)


@router.get("", response_model=list[ReelCheckResponse])
def list_reel_checks():
    rows = db.fetch_all("SELECT * FROM reel_checks ORDER BY created_at DESC")
    return [_row_to_response(r) for r in rows]


@router.get("/{check_id}", response_model=ReelCheckResponse)
def get_reel_check(check_id: str):
    row = db.fetch_one("SELECT * FROM reel_checks WHERE id=?", (check_id,))
    if not row:
        raise HTTPException(404, "reel check not found")
    return _row_to_response(row)


@router.get("/{check_id}/claims/{claim_index}/clip")
def get_claim_clip(check_id: str, claim_index: int):
    row = db.fetch_one("SELECT claims_json FROM reel_checks WHERE id=?", (check_id,))
    if not row or not row["claims_json"]:
        raise HTTPException(404, "reel check or claims not found")
    claims = json.loads(row["claims_json"])
    if claim_index < 0 or claim_index >= len(claims):
        raise HTTPException(404, "claim not found")
    claim = claims[claim_index]

    check_dir = settings.data_dir / "reel_checks" / check_id
    source_matches = sorted(check_dir.glob("source.*"))
    if not source_matches:
        raise HTTPException(
            404, "the source video for this check is no longer available (checks run before "
            "clip downloads were added didn't keep it)"
        )

    clip_path = check_dir / "clips" / f"{claim_index}.mp4"
    if not clip_path.exists():
        cut_claim_clip(source_matches[0], claim["start_seconds"], claim["end_seconds"], clip_path)

    return FileResponse(clip_path, media_type="video/mp4", filename=f"claim_{claim_index + 1}.mp4")


def _script_row_to_response(row) -> DebunkScriptResponse:
    d = dict(row)
    script = json.loads(d["script_json"]) if d["script_json"] else {}
    return DebunkScriptResponse(
        id=d["id"], check_id=d["check_id"], status=d["status"],
        title=script.get("title"), intro_hook=script.get("intro_hook"),
        beats=script.get("beats", []), outro_cta=script.get("outro_cta"),
        error_message=d["error_message"],
        created_at=d["created_at"], completed_at=d["completed_at"],
    )


@router.post("/{check_id}/debunk-script", response_model=DebunkScriptResponse)
async def create_debunk_script_route(check_id: str):
    check = db.fetch_one("SELECT status FROM reel_checks WHERE id=?", (check_id,))
    if not check:
        raise HTTPException(404, "reel check not found")
    if check["status"] != "done":
        raise HTTPException(409, "reel check hasn't finished fact-checking yet")

    script_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO debunk_scripts (id, check_id, status) VALUES (?, ?, 'generating')",
        (script_id, check_id),
    )
    asyncio.create_task(run_debunk_script(script_id, check_id))
    row = db.fetch_one("SELECT * FROM debunk_scripts WHERE id=?", (script_id,))
    return _script_row_to_response(row)


@router.get("/{check_id}/debunk-script/{script_id}", response_model=DebunkScriptResponse)
def get_debunk_script_route(check_id: str, script_id: str):
    row = db.fetch_one("SELECT * FROM debunk_scripts WHERE id=? AND check_id=?", (script_id, check_id))
    if not row:
        raise HTTPException(404, "debunk script not found")
    return _script_row_to_response(row)


@router.get("/{check_id}/debunk-script/{script_id}/pdf")
def get_debunk_script_pdf_route(check_id: str, script_id: str):
    row = db.fetch_one("SELECT * FROM debunk_scripts WHERE id=? AND check_id=?", (script_id, check_id))
    if not row or row["status"] != "done" or not row["pdf_path"]:
        raise HTTPException(404, "debunk script PDF not ready")
    return FileResponse(row["pdf_path"], media_type="application/pdf", filename="debunk_reel_script.pdf")
