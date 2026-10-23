from fastapi import APIRouter
from pydantic import BaseModel

from app.search.aggregator import run_search

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    sources: list[str] | None = None


@router.post("")
async def search(req: SearchRequest):
    return await run_search(req.query, req.sources)
