import asyncio
import uuid

import httpx

from app.core import db
from app.core.config import settings
from app.search import instagram, web, youtube

SOURCES = {"youtube": youtube, "web": web, "instagram": instagram}


async def run_search(query: str, sources: list[str] | None = None) -> dict:
    sources = [s for s in (sources or list(SOURCES.keys())) if s in SOURCES]
    search_id = str(uuid.uuid4())
    db.execute("INSERT INTO searches (id, query) VALUES (?, ?)", (search_id, query))

    async with httpx.AsyncClient(timeout=15) as client:
        coros = []
        for name in sources:
            mod = SOURCES[name]
            if name == "youtube":
                coros.append(mod.search(client, query, settings.max_results_per_source, settings.youtube_api_key))
            else:
                coros.append(mod.search(client, query, settings, settings.max_results_per_source))
        outcomes = await asyncio.gather(*coros, return_exceptions=True)

    results = []
    errors: dict[str, str] = {}
    for name, outcome in zip(sources, outcomes):
        if isinstance(outcome, Exception):
            errors[name] = str(outcome)
            continue
        for item in outcome:
            result_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO search_results "
                "(id, search_id, source, title, url, thumbnail_url, description, published_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result_id, search_id, item["source"], item["title"], item["url"],
                    item.get("thumbnail_url"), item.get("description", ""), item.get("published_at"),
                ),
            )
            results.append({
                **item,
                "id": result_id,
                "search_id": search_id,
                "status": "pending",
                "video_path": None,
                "error_message": None,
            })

    return {"search_id": search_id, "query": query, "results": results, "errors": errors}
