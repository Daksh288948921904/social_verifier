import re

import httpx

from app.core.config import Settings
from app.search import google_cse

# Instagram has no public search API, so reels are discovered indirectly via
# a site-restricted Google Custom Search query (the CSE must have "Search
# the entire web" enabled) and filtered down to links that actually look
# like a reel/post, since a site: query can still surface Instagram profile
# pages, hashtag pages, etc.
_REEL_URL_RE = re.compile(r"instagram\.com/(reel|p)/")


async def search(client: httpx.AsyncClient, query: str, settings: Settings, max_results: int) -> list[dict]:
    items = await google_cse.search(
        client, f"site:instagram.com/reel {query}",
        settings.google_cse_api_key, settings.google_cse_cx, max_results,
    )
    results = [item for item in items if _REEL_URL_RE.search(item["url"])]
    for item in results:
        item["source"] = "instagram"
    return results
