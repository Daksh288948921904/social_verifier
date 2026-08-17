"""Ingestion helpers that populate the Indian-government source corpus (see
app/rag/gov_store.py) that claim verification retrieves from for grounding.
Called from scripts/ingest_gov_sources.py -- nothing here runs on import,
since these make outbound network calls and write to Qdrant, and should only
happen when a user explicitly (re)builds the corpus.
"""
import logging
from html.parser import HTMLParser

import httpx

from app.core.config import settings
from app.rag.gov_store import index_gov_document

logger = logging.getLogger(__name__)

DATA_GOV_IN_BASE = "https://api.data.gov.in/resource"


class _TextExtractor(HTMLParser):
    """Minimal HTML-to-text extractor: strips tags/scripts/styles, keeps
    visible text. No external dependency needed -- page structure doesn't
    matter here, only the readable prose that gets chunked and embedded."""

    def __init__(self):
        super().__init__()
        self._skip = False
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


def fetch_data_gov_in_resource(resource_id: str, limit: int = 500) -> list[dict]:
    """Fetches records from one data.gov.in / OGD Platform India dataset
    (https://www.data.gov.in/apis -- free signup for an API key). Returns []
    if no API key is configured rather than raising, so ingesting other
    sources can still proceed without one."""
    if not settings.data_gov_in_api_key:
        logger.warning("data_gov_in_api_key not configured; skipping resource %s", resource_id)
        return []
    response = httpx.get(
        f"{DATA_GOV_IN_BASE}/{resource_id}",
        params={"api-key": settings.data_gov_in_api_key, "format": "json", "limit": limit},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json().get("records", [])


def ingest_data_gov_in_dataset(resource_id: str, title: str, category: str) -> int:
    """Fetches one data.gov.in dataset and indexes its records as grounding
    text, tagged with the dataset's title/category/source URL so
    verify_claim() can cite it."""
    records = fetch_data_gov_in_resource(resource_id)
    if not records:
        return 0
    url = f"https://www.data.gov.in/resource/{resource_id}"
    text = "\n".join(", ".join(f"{k}: {v}" for k, v in record.items()) for record in records)
    return index_gov_document(f"datagovin:{resource_id}", url, title, category, text)


def ingest_url(url: str, title: str, category: str) -> int:
    """Fetches and indexes a single official page (a PIB press release, an
    RBI/MOSPI publication, an Indian Kanoon judgment, etc.) as grounding
    text. Meant for a small, hand-curated list of specific URLs (see
    scripts/ingest_gov_sources.py) -- this does not crawl or discover pages
    on its own."""
    response = httpx.get(url, timeout=30.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    text = _html_to_text(response.text)
    return index_gov_document(url, url, title, category, text)
