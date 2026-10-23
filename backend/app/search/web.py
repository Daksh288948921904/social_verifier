import httpx

from app.core.config import Settings
from app.search import google_cse


async def search(client: httpx.AsyncClient, query: str, settings: Settings, max_results: int) -> list[dict]:
    items = await google_cse.search(
        client, query, settings.google_cse_api_key, settings.google_cse_cx, max_results,
    )
    for item in items:
        item["source"] = "web"
    return items
