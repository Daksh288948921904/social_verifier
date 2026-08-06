from qdrant_client import QdrantClient

from app.core.config import settings

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        if not settings.qdrant_url:
            raise RuntimeError("QDRANT_URL is not configured (set it in backend/.env)")
        _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    return _client
