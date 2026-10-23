import httpx

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def search(client: httpx.AsyncClient, query: str, max_results: int, api_key: str) -> list[dict]:
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured")
    resp = await client.get(SEARCH_URL, params={
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "key": api_key,
    })
    resp.raise_for_status()
    data = resp.json()

    items = []
    for item in data.get("items", []):
        video_id = item["id"]["videoId"]
        snippet = item["snippet"]
        thumbs = snippet.get("thumbnails", {})
        thumb = thumbs.get("medium") or thumbs.get("default") or {}
        items.append({
            "source": "youtube",
            "title": snippet.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "video_id": video_id,
            "channel": snippet.get("channelTitle", ""),
            "thumbnail_url": thumb.get("url"),
            "description": snippet.get("description", ""),
            "published_at": snippet.get("publishedAt"),
        })
    return items
