import html
import json
import logging
import subprocess

import httpx

from app.core.config import settings
from app.search import youtube

logger = logging.getLogger(__name__)


async def search_videos(query: str, limit: int) -> list[dict]:
    """YouTube Data API first; yt-dlp's own ytsearch as a fallback. The API's
    search call costs 100 of the default 10,000 daily quota units (so ~100
    keywords a day), and a batched script project burns through that fast --
    when the key is missing or the quota is spent, scraping the results page
    via yt-dlp still works, just slower."""
    if settings.youtube_api_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                items = await youtube.search(client, query, limit, settings.youtube_api_key)
            return [
                {
                    "video_id": item["video_id"],
                    "title": html.unescape(item["title"]),
                    "channel": html.unescape(item.get("channel", "")),
                    "description": html.unescape(item.get("description", "")),
                    "thumbnail_url": item.get("thumbnail_url"),
                    "published_at": item.get("published_at"),
                    "duration_seconds": None,
                }
                for item in items
            ]
        except Exception as e:
            logger.warning("YouTube API search failed for %r, falling back to yt-dlp: %s", query, e)
    return _ytdlp_search(query, limit)


def _ytdlp_search(query: str, limit: int) -> list[dict]:
    result = subprocess.run(
        [settings.ytdlp_bin, "--flat-playlist", "-J", "--no-warnings", f"ytsearch{limit}:{query}"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"YouTube search failed: {result.stderr.strip()[-300:]}")
    entries = json.loads(result.stdout).get("entries") or []
    videos = []
    for e in entries:
        if not e.get("id"):
            continue
        thumbs = e.get("thumbnails") or []
        videos.append({
            "video_id": e["id"],
            "title": e.get("title") or "",
            "channel": e.get("channel") or e.get("uploader") or "",
            "description": e.get("description") or "",
            "thumbnail_url": thumbs[-1]["url"] if thumbs else f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg",
            "published_at": None,
            "duration_seconds": e.get("duration"),
        })
    return videos
