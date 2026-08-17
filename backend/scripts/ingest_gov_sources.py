"""Populates the Indian-government source corpus (app/rag/gov_store.py) that
claim verification retrieves from for grounding (see
app/verifier/claims.py::verify_claim). Run manually, and re-run any time to
refresh:

    python scripts/ingest_gov_sources.py

Edit SOURCES below to add/remove datasets and pages -- this is a curated
allowlist, not a crawler, so nothing is indexed unless it's listed here.
Categories are freeform strings used only for optional filtering in
gov_store.search_gov_sources(); "economic", "company", "court", and
"political" match the claim types this was built for, but any string works.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.gov_ingest import ingest_data_gov_in_dataset, ingest_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# data.gov.in resource IDs -- find these on a dataset's page at data.gov.in
# under "API" (needs a free API key from https://data.gov.in/user/register,
# set as DATA_GOV_IN_API_KEY in backend/.env). (resource_id, title, category).
DATA_GOV_IN_DATASETS: list[tuple[str, str, str]] = [
    # Example once you've picked real datasets:
    # ("9ef84268-d588-465a-a308-a864a43d0070", "GDP growth rate series", "economic"),
]

# Individual official pages to fetch and index as-is -- PIB press releases,
# RBI/MOSPI publications, Indian Kanoon judgments, etc. (url, title, category).
URL_SOURCES: list[tuple[str, str, str]] = [
    # Example:
    # ("https://pib.gov.in/PressReleasePage.aspx?PRID=...", "PIB: <headline>", "political"),
]


def main() -> None:
    total = 0
    for resource_id, title, category in DATA_GOV_IN_DATASETS:
        try:
            n = ingest_data_gov_in_dataset(resource_id, title, category)
            logger.info("Indexed %d chunk(s) from data.gov.in resource %s", n, resource_id)
            total += n
        except Exception:
            logger.exception("Failed to ingest data.gov.in resource %s", resource_id)

    for url, title, category in URL_SOURCES:
        try:
            n = ingest_url(url, title, category)
            logger.info("Indexed %d chunk(s) from %s", n, url)
            total += n
        except Exception:
            logger.exception("Failed to ingest %s", url)

    logger.info("Done -- %d chunk(s) indexed total", total)


if __name__ == "__main__":
    main()
