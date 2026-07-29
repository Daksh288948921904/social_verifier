from openai import OpenAI

from app.core.config import settings

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured (set it in backend/.env)")
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client
