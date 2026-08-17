import logging
import uuid

from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.core.config import settings
from app.core.qdrant_client import get_client
from app.rag.chunking import chunk_text
from app.rag.embeddings import DIMENSIONS, embed_text

logger = logging.getLogger(__name__)

# Distinct from claim_store's namespace -- this indexes ingested Indian
# government source documents (see gov_ingest.py / scripts/ingest_gov_sources.py),
# a separate global corpus from per-video claim chunks, so point IDs must
# never collide with claim_store's even if a source_id happened to match a
# check_id.
_POINT_NAMESPACE = uuid.UUID("8f1c2a6b-4e9d-4a3f-9c1b-2d7e6a0f5b3c")


def _point_id(source_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{source_id}:{chunk_index}"))


def ensure_gov_collection() -> None:
    client = get_client()
    if not client.collection_exists(settings.qdrant_gov_collection):
        client.create_collection(
            collection_name=settings.qdrant_gov_collection,
            vectors_config=VectorParams(size=DIMENSIONS, distance=Distance.COSINE),
        )


def index_gov_document(source_id: str, url: str, title: str, category: str, text: str) -> int:
    """Chunks and embeds one government source document and upserts it into
    the gov-sources Qdrant collection, tagged with its url/title/category so
    verify_claim() can retrieve and cite it. Re-ingesting the same source_id
    overwrites its old points (deterministic IDs) instead of duplicating
    them, so re-running the ingest script is always safe. Returns the number
    of chunks indexed."""
    chunks = chunk_text(text)
    if not chunks:
        return 0

    ensure_gov_collection()
    client = get_client()
    points = [
        PointStruct(
            id=_point_id(source_id, i),
            vector=embed_text(chunk),
            payload={
                "source_id": source_id, "url": url, "title": title,
                "category": category, "chunk_index": i, "text": chunk,
            },
        )
        for i, chunk in enumerate(chunks)
    ]
    client.upsert(collection_name=settings.qdrant_gov_collection, points=points)
    return len(points)


def search_gov_sources(query_text: str, top_k: int = 5, category: str | None = None) -> list[dict]:
    """Retrieves the top-k chunks from the indexed Indian-government source
    corpus most relevant to query_text, optionally restricted to one
    category (e.g. "economic", "company", "court", "political"). Returns []
    if the collection doesn't exist yet (nothing ingested), same as an empty
    corpus -- this is the real grounding signal verify_claim() uses for
    official_sources, not a guess parsed out of a model's self-reported
    answer."""
    client = get_client()
    if not client.collection_exists(settings.qdrant_gov_collection):
        return []

    query_filter = None
    if category:
        query_filter = Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])

    result = client.query_points(
        collection_name=settings.qdrant_gov_collection,
        query=embed_text(query_text),
        query_filter=query_filter,
        limit=top_k,
    )
    return [
        {
            "text": p.payload["text"], "url": p.payload["url"],
            "title": p.payload["title"], "category": p.payload["category"],
        }
        for p in result.points if p.payload
    ]
