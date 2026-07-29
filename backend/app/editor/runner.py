import asyncio
import json
import logging
from pathlib import Path

from app.core import db
from app.core.config import settings
from app.editor.compile import compile_timeline
from app.verifier.clip_cutter import cut_claim_clip

logger = logging.getLogger(__name__)


def _resolve_item(check_dir: Path, source_path: Path | None, claims: list[dict], item: dict) -> Path:
    if item["type"] == "claim":
        if source_path is None:
            raise ValueError(
                "The source video for this check is no longer available, so its claim "
                "clips can't be cut."
            )
        idx = item["claim_index"]
        claim = claims[idx]
        clip_path = check_dir / "clips" / f"{idx}.mp4"
        if not clip_path.exists():
            cut_claim_clip(source_path, claim["start_seconds"], claim["end_seconds"], clip_path)
        return clip_path

    if item["type"] == "upload":
        row = db.fetch_one("SELECT video_path FROM editor_uploads WHERE id=?", (item["upload_id"],))
        if not row:
            raise ValueError(f"Uploaded video {item['upload_id']} not found.")
        return Path(row["video_path"])

    raise ValueError(f"Unknown timeline item type: {item['type']!r}")


async def run_compile(export_id: str, check_id: str, items: list[dict]) -> None:
    """One-shot background job: resolve every timeline item to a real clip
    path (cutting claim clips on demand, same as the single-clip download
    endpoint) and concatenate them in order. Mirrors the verify pipeline's
    status-in-a-DB-row pattern so the frontend can poll it."""
    try:
        if not items:
            raise ValueError("The timeline is empty -- add some clips before compiling.")

        check_row = db.fetch_one("SELECT claims_json FROM reel_checks WHERE id=?", (check_id,))
        claims = json.loads(check_row["claims_json"]) if check_row and check_row["claims_json"] else []

        check_dir = settings.data_dir / "reel_checks" / check_id
        source_matches = sorted(check_dir.glob("source.*"))
        source_path = source_matches[0] if source_matches else None

        clip_paths = [
            await asyncio.to_thread(_resolve_item, check_dir, source_path, claims, item)
            for item in items
        ]

        output_path = check_dir / "exports" / f"{export_id}.mp4"
        await asyncio.to_thread(compile_timeline, clip_paths, output_path)

        db.execute(
            "UPDATE editor_exports SET status='done', output_path=?, completed_at=datetime('now') "
            "WHERE id=?",
            (str(output_path), export_id),
        )
    except Exception as e:
        logger.exception("Editor compile %s failed", export_id)
        db.execute(
            "UPDATE editor_exports SET status='error', error_message=?, completed_at=datetime('now') "
            "WHERE id=?",
            (str(e), export_id),
        )
