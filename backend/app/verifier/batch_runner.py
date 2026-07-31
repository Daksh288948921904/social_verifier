import logging

from app.core import db
from app.verifier.runner import run_reel_check

logger = logging.getLogger(__name__)


async def run_batch(batch_id: str, check_ids: list[tuple[str, str]]) -> None:
    """Processes every (check_id, url) pair strictly one at a time --
    run_reel_check is awaited directly rather than scheduled as its own task,
    so the next one doesn't start until the previous fully finishes (or
    fails). Deliberately sequential: running these concurrently would
    multiply how fast this app burns through the shared Groq/OpenAI rate
    limits. Rows are already inserted (status='queued') by the caller before
    this runs, so polling the batch always shows the full list."""
    for check_id, url in check_ids:
        try:
            await run_reel_check(check_id, url)
        except Exception:
            # run_reel_check already catches its own failures and writes
            # status='error' to this row -- this is only a last-resort
            # guard so one broken URL can't ever kill the rest of the batch.
            logger.exception("Unexpected failure processing %s in batch %s", url, batch_id)

    db.execute(
        "UPDATE verify_batches SET status='done', completed_at=datetime('now') WHERE id=?",
        (batch_id,),
    )
