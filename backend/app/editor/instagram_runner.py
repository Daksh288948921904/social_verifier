import asyncio
import logging

from app.core import db
from app.core.config import settings
from app.editor.instagram_kit import generate_caption_kit, generate_thumbnail

logger = logging.getLogger(__name__)


async def run_instagram_kit(kit_id: str, check_id: str) -> None:
    """One-shot background job: generate the AI thumbnail image and the
    caption/timing/audio-style text kit for posting this check's compiled
    video to Instagram. Mirrors the reel-check/compile status-in-a-DB-row
    pattern so the frontend can poll it."""
    try:
        thumbnail_path = settings.data_dir / "reel_checks" / check_id / "instagram" / f"{kit_id}.png"
        await asyncio.to_thread(generate_thumbnail, check_id, thumbnail_path)

        kit = await asyncio.to_thread(generate_caption_kit, check_id)

        db.execute(
            "UPDATE instagram_kits SET status='done', thumbnail_path=?, caption=?, "
            "best_time=?, audio_style=?, completed_at=datetime('now') WHERE id=?",
            (str(thumbnail_path), kit["caption"], kit["best_time"], kit["audio_style"], kit_id),
        )
    except Exception as e:
        logger.exception("Instagram kit %s failed", kit_id)
        db.execute(
            "UPDATE instagram_kits SET status='error', error_message=?, completed_at=datetime('now') "
            "WHERE id=?",
            (str(e), kit_id),
        )
