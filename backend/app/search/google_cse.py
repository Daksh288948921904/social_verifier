import httpx

CSE_URL = "https://www.googleapis.com/customsearch/v1"


async def search(
    client: httpx.AsyncClient, query: str, api_key: str, cx: str, max_results: int,
) -> list[dict]:
    """Thin wrapper around the Google Custom Search JSON API, shared by
    app/search/web.py (general web/news) and app/search/instagram.py
    (Instagram has no public search API, so it's discovered via a
    site:instagram.com/reel CSE query instead)."""
    if not api_key or not cx:
        raise RuntimeError("GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX is not configured")
    resp = await client.get(CSE_URL, params={
        "key": api_key, "cx": cx, "q": query, "num": min(max_results, 10),
    })
    resp.raise_for_status()
    data = resp.json()

    items = []
    for item in data.get("items", []):
        pagemap = item.get("pagemap", {})
        thumb_list = pagemap.get("cse_thumbnail") or pagemap.get("cse_image")
        items.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "thumbnail_url": thumb_list[0].get("src") if thumb_list else None,
            "description": item.get("snippet", ""),
            "published_at": None,
        })
    return items
