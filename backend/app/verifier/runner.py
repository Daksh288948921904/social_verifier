import asyncio
import json
import logging
import tempfile
from pathlib import Path

from app.core import db
from app.core.config import settings
from app.verifier.claims import (
    ClaimVerification,
    extract_claims,
    generate_conclusion,
    verify_claim,
    verify_claim_to_dict,
)
from app.verifier.clip_match import attach_clip_times
from app.verifier.download import download_clip, extract_audio
from app.verifier.manuscript import build_manuscript

logger = logging.getLogger(__name__)


def _set_status(check_id: str, status: str, progress: str = "") -> None:
    db.execute(
        "UPDATE reel_checks SET status=?, progress=? WHERE id=?",
        (status, progress, check_id),
    )


async def run_reel_check(check_id: str, url: str) -> None:
    """One-shot background pipeline: download -> transcribe -> extract
    claims -> verify each claim. Runs as a detached asyncio task kicked off
    by the API endpoint; all state lives in the reel_checks row so the
    frontend can poll it, mirroring the live-session status pattern."""
    try:
        # The source video is downloaded into a permanent, per-check
        # directory (not the temp dir below) so a clip of each claim's
        # exact quote can still be cut on demand after this pipeline
        # finishes -- everything else here is transient working data.
        check_dir = settings.data_dir / "reel_checks" / check_id
        _set_status(check_id, "downloading")
        video_path = await asyncio.to_thread(download_clip, url, check_dir)

        with tempfile.TemporaryDirectory(prefix="reel_check_") as tmp:
            tmp_dir = Path(tmp)

            _set_status(check_id, "transcribing")
            raw_audio = tmp_dir / "audio_raw.wav"
            processed_audio = tmp_dir / "audio_dsp.wav"
            await asyncio.to_thread(extract_audio, video_path, raw_audio)
            manuscript, segments = await asyncio.to_thread(build_manuscript, raw_audio, processed_audio)

            db.execute("UPDATE reel_checks SET manuscript=? WHERE id=?", (manuscript, check_id))

            _set_status(check_id, "extracting_claims")
            claims = await asyncio.to_thread(extract_claims, manuscript)
            claims = attach_clip_times(claims, segments)

            verifications: list[ClaimVerification] = []
            verification_dicts = []
            for i, claim in enumerate(claims):
                _set_status(check_id, "verifying_claims", f"{i + 1}/{len(claims)}")
                verification = await asyncio.to_thread(verify_claim, claim)
                verifications.append(verification)
                verification_dicts.append(verify_claim_to_dict(verification))
                # Persist incrementally so a slow/failed later claim doesn't
                # lose already-verified ones, and the frontend can show
                # results as they arrive instead of only at the very end.
                db.execute(
                    "UPDATE reel_checks SET claims_json=? WHERE id=?",
                    (json.dumps(verification_dicts), check_id),
                )

            _set_status(check_id, "concluding")
            conclusion = await asyncio.to_thread(generate_conclusion, verifications)
            db.execute("UPDATE reel_checks SET conclusion=? WHERE id=?", (conclusion, check_id))

            db.execute(
                "UPDATE reel_checks SET status='done', progress='', completed_at=datetime('now') "
                "WHERE id=?",
                (check_id,),
            )
    except Exception as e:
        logger.exception("Reel check %s failed", check_id)
        db.execute(
            "UPDATE reel_checks SET status='error', error_message=?, completed_at=datetime('now') "
            "WHERE id=?",
            (str(e), check_id),
        )
