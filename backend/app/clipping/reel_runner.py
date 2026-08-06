import asyncio
import logging
import tempfile
from pathlib import Path

from app.clipping.reel_export import build_overlay_track, generate_hook_and_style, render_reel
from app.core import db
from app.core.config import settings

logger = logging.getLogger(__name__)


async def run_reel_export(reel_id: str, clip_id: str) -> None:
    """One-shot background job: write the hook/audio-style text, build the
    single hook+captions overlay track from this clip's transcript segments,
    then composite it onto the clip via ffmpeg. Mirrors the status-in-a-DB-
    row polling pattern used by every other background feature in this app."""
    try:
        clip = db.fetch_one("SELECT video_path FROM clips WHERE id=?", (clip_id,))
        reel_dir = settings.data_dir / "reels" / clip_id
        output_path = reel_dir / f"{reel_id}.mp4"

        kit = await asyncio.to_thread(generate_hook_and_style, clip_id)

        with tempfile.TemporaryDirectory(prefix="reel_overlays_") as tmp:
            work_dir = Path(tmp)
            overlay_track = await asyncio.to_thread(
                build_overlay_track, clip_id, kit["hook"], work_dir,
            )
            await asyncio.to_thread(
                render_reel, Path(clip["video_path"]), overlay_track, output_path,
            )

        db.execute(
            "UPDATE clip_reels SET status='done', hook_text=?, audio_style=?, output_path=?, "
            "completed_at=datetime('now') WHERE id=?",
            (kit["hook"], kit["audio_style"], str(output_path), reel_id),
        )
    except Exception as e:
        logger.exception("Reel export %s failed", reel_id)
        db.execute(
            "UPDATE clip_reels SET status='error', error_message=?, completed_at=datetime('now') "
            "WHERE id=?",
            (str(e), reel_id),
        )
