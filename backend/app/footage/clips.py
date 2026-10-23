import asyncio
import logging
import re
import subprocess
import unicodedata
from pathlib import Path

from app.core import db
from app.core.config import settings
from app.core.ytdlp_cookies import cookies_args

logger = logging.getLogger(__name__)

MAX_CLIP_SECONDS = 600
# Clip downloads are ffmpeg re-encodes on top of a YouTube fetch -- a couple
# at a time keeps the box (and YouTube's rate limiting) happy.
_download_slots = asyncio.Semaphore(2)


class ClipDownloadError(RuntimeError):
    pass


def clip_filename(segment_position: int, label: str, start: float) -> str:
    """e.g. "S01_Defendants-in-the-dock_0m57s.mp4" -- sorts by segment in a
    file browser and still says what the clip is once it's out of the app."""
    # Fold accents to plain letters first ("Göring" -> "Goring") so names
    # stay readable instead of losing those letters to the dash filter.
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_label).strip("-")[:50] or "clip"
    m, s = divmod(int(start), 60)
    return f"S{segment_position + 1:02d}_{slug}_{m}m{s:02d}s.mp4"


def download_section(video_id: str, start: float, end: float, dest: Path) -> Path:
    """Fetches just [start, end] of a YouTube video rather than the whole
    thing (a moment is often 15s of an 80-minute documentary). Keyframes are
    forced at the cut points so the clip starts on the exact frame instead
    of snapping back to the previous keyframe, which can be seconds early."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    template = dest.with_suffix(".%(ext)s")
    cmd = [
        settings.ytdlp_bin, "--no-warnings", "--no-playlist",
        # 720p is plenty for an edit timeline and keeps re-encodes quick.
        "-f", "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
        "--download-sections", f"*{start:.2f}-{end:.2f}",
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(template),
    ]
    with cookies_args(settings.ytdlp_youtube_cookies_file) as cookie_args:
        try:
            result = subprocess.run(
                [*cmd, *cookie_args, f"https://www.youtube.com/watch?v={video_id}"],
                capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            raise ClipDownloadError("Download timed out after 10 minutes")
    if result.returncode != 0 or not dest.exists():
        lines = [l for l in result.stderr.strip().splitlines() if "ERROR" in l] or result.stderr.strip().splitlines()
        raise ClipDownloadError(lines[-1] if lines else "yt-dlp produced no file")
    return dest


async def run_clip_download(clip_id: str) -> None:
    async with _download_slots:
        try:
            clip = db.fetch_one("SELECT * FROM footage_clips WHERE id=?", (clip_id,))
            dest = settings.data_dir / "footage_clips" / clip["project_id"] / f"{clip_id}.mp4"
            await asyncio.to_thread(
                download_section, clip["video_id"], clip["start_seconds"], clip["end_seconds"], dest,
            )
            db.execute(
                "UPDATE footage_clips SET status='done', file_path=?, completed_at=datetime('now') WHERE id=?",
                (str(dest), clip_id),
            )
        except Exception as e:
            logger.warning("Footage clip %s failed: %s", clip_id, e)
            db.execute(
                "UPDATE footage_clips SET status='error', error_message=?, completed_at=datetime('now') "
                "WHERE id=?",
                (str(e), clip_id),
            )
