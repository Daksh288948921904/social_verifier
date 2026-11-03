import asyncio
import logging

import re

from app.core import db
from app.core.config import settings
from app.footage.clips import ClipDownloadError, download_section
from app.search.fetch import DownloadError, cookies_for_source, download_clip
from app.search.smart_clip import SmartClipError, find_clean_clip

logger = logging.getLogger(__name__)

# Each smart clip grabs ~30 frames with ffmpeg, makes a few vision calls and
# cuts a section with yt-dlp -- two at a time keeps the box and YouTube happy.
_smart_slots = asyncio.Semaphore(2)
_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})")


def _smart(result_id: str, **fields) -> None:
    sets = ", ".join(f"smart_{k}=?" for k in fields)
    db.execute(f"UPDATE search_results SET {sets} WHERE id=?", (*fields.values(), result_id))


async def run_smart_clip(result_id: str, seconds: float) -> None:
    """Background job: find a clean (no ticker/logo/text) 8-10s stretch of a
    YouTube result that fits the search, then cut just that section."""
    try:
        row = db.fetch_one(
            "SELECT r.url, s.query FROM search_results r JOIN searches s ON s.id = r.search_id WHERE r.id=?",
            (result_id,),
        )
        match = _VIDEO_ID_RE.search(row["url"] or "")
        if not match:
            raise SmartClipError("Smart clips work on YouTube videos only")
        video_id = match.group(1)
        async with _smart_slots:
            _smart(result_id, note="Checking frames for tickers, logos and text…")
            pick = await asyncio.to_thread(find_clean_clip, video_id, row["query"], seconds)
            _smart(result_id, start=pick.start, end=pick.end, note="Cutting the clip…")
            dest = settings.data_dir / "search_clips" / result_id / f"smart_{int(pick.start)}-{int(pick.end)}.mp4"
            await asyncio.to_thread(download_section, video_id, pick.start, pick.end, dest)
        shot = "one continuous shot" if pick.single_shot else "includes a cut"
        _smart(result_id, status="done", path=str(dest),
               note=f"{pick.shows} · {shot} · {pick.checked} frames checked")
    except SmartClipError as e:
        _smart(result_id, status="none", note=str(e))
    except ClipDownloadError as e:
        _smart(result_id, status="error", note=f"Found a clean stretch but the download failed: {e}")
    except Exception as e:
        logger.exception("Smart clip %s crashed", result_id)
        _smart(result_id, status="error", note=str(e))


def recover_interrupted() -> None:
    """Background jobs live only in this process -- anything mid-flight when
    the server stopped is orphaned, so let the user run it again."""
    db.execute(
        "UPDATE search_results SET smart_status='error', "
        "smart_note='Interrupted by a server restart -- run it again.' WHERE smart_status='analyzing'"
    )
    db.execute(
        "UPDATE search_results SET status='error', "
        "error_message='Interrupted by a server restart -- fetch it again.' WHERE status='fetching'"
    )


async def run_fetch(result_id: str) -> None:
    """Background job: status-in-a-DB-row pattern, same as clip_reels'
    run_reel_export -- the blocking yt-dlp subprocess runs via
    asyncio.to_thread so it doesn't stall the event loop."""
    try:
        row = db.fetch_one("SELECT url, source FROM search_results WHERE id=?", (result_id,))
        dest_dir = settings.data_dir / "search_clips" / result_id
        cookies_file = cookies_for_source(row["source"])
        video_path = await asyncio.to_thread(download_clip, row["url"], dest_dir, cookies_file)
        db.execute(
            "UPDATE search_results SET status='done', video_path=? WHERE id=?",
            (str(video_path), result_id),
        )
    except DownloadError as e:
        logger.warning("Search fetch %s failed: %s", result_id, e)
        db.execute(
            "UPDATE search_results SET status='error', error_message=? WHERE id=?",
            (str(e), result_id),
        )
    except Exception as e:
        logger.exception("Search fetch %s crashed", result_id)
        db.execute(
            "UPDATE search_results SET status='error', error_message=? WHERE id=?",
            (str(e), result_id),
        )
