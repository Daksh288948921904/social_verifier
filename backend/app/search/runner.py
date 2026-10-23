import asyncio
import logging

from app.core import db
from app.core.config import settings
from app.search.fetch import DownloadError, cookies_for_source, download_clip

logger = logging.getLogger(__name__)


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
