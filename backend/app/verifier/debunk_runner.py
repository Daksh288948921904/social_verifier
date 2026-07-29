import asyncio
import json
import logging

from app.core import db
from app.core.config import settings
from app.verifier.debunk_script import generate_script, render_pdf

logger = logging.getLogger(__name__)


async def run_debunk_script(script_id: str, check_id: str) -> None:
    """One-shot background job: write a humor-forward debunk Reel script from
    this check's claims/conclusion, then render it to a downloadable PDF.
    Mirrors the reel-check/instagram-kit status-in-a-DB-row polling pattern."""
    try:
        script = await asyncio.to_thread(generate_script, check_id)

        pdf_path = settings.data_dir / "reel_checks" / check_id / "debunk_scripts" / f"{script_id}.pdf"
        await asyncio.to_thread(render_pdf, script, pdf_path)

        db.execute(
            "UPDATE debunk_scripts SET status='done', script_json=?, pdf_path=?, "
            "completed_at=datetime('now') WHERE id=?",
            (json.dumps(script), str(pdf_path), script_id),
        )
    except Exception as e:
        logger.exception("Debunk script %s failed", script_id)
        db.execute(
            "UPDATE debunk_scripts SET status='error', error_message=?, completed_at=datetime('now') "
            "WHERE id=?",
            (str(e), script_id),
        )
