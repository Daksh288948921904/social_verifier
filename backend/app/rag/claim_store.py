import logging
import uuid

from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, Range, VectorParams

from app.core.config import settings
from app.core.qdrant_client import get_client
from app.rag.chunking import chunk_text
from app.rag.embeddings import DIMENSIONS, embed_text

logger = logging.getLogger(__name__)

# Fixed namespace so point IDs are deterministic from (check_id, claim_index,
# chunk_index) -- re-indexing the same claim (e.g. a retried pipeline run)
# overwrites its old points instead of duplicating them.
_POINT_NAMESPACE = uuid.UUID("2b6e0f4e-6a3a-4c1a-9e0b-7f3a5c9d1e2f")


def _point_id(check_id: str, claim_index: int, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{check_id}:{claim_index}:{chunk_index}"))


def ensure_collection() -> None:
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=DIMENSIONS, distance=Distance.COSINE),
        )


def index_claim(check_id: str, claim_index: int, quote: str, claim_text: str, analysis: str = "") -> None:
    """Chunks and embeds one claim's text and upserts it into Qdrant, tagged
    with its check_id + claim_index (the "claim number"). Called after a
    claim is verified so later claims in the same video can retrieve it as
    context -- see search_prior_context()."""
    parts = [f"Claim: {claim_text}", f"Quote: {quote}"]
    if analysis:
        parts.append(f"Analysis: {analysis}")
    chunks = chunk_text("\n".join(parts))
    if not chunks:
        return

    client = get_client()
    points = [
        PointStruct(
            id=_point_id(check_id, claim_index, i),
            vector=embed_text(chunk),
            payload={"check_id": check_id, "claim_index": claim_index, "chunk_index": i, "text": chunk},
        )
        for i, chunk in enumerate(chunks)
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)


def search_prior_context(check_id: str, claim_index: int, query_text: str, top_k: int = 3) -> list[str]:
    """Retrieves the top-k chunks from claims earlier than claim_index in the
    same video (check_id), most relevant to query_text first. Used to give a
    continuation claim ("he also said...") the context of what an earlier
    claim in the same video actually established."""
    if claim_index <= 0:
        return []

    client = get_client()
    query_filter = Filter(must=[
        FieldCondition(key="check_id", match=MatchValue(value=check_id)),
        FieldCondition(key="claim_index", range=Range(lt=claim_index)),
    ])
    result = client.query_points(
        collection_name=settings.qdrant_collection,
        query=embed_text(query_text),
        query_filter=query_filter,
        limit=top_k,
    )
    return [point.payload["text"] for point in result.points if point.payload]
