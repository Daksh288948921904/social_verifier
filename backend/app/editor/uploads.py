import subprocess
import uuid
from pathlib import Path

from app.core import db
from app.core.config import settings


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            settings.ffprobe_bin, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, timeout=15,
    )
    try:
        return float(result.stdout.strip() or 0.0)
    except ValueError:
        return 0.0


def save_upload(check_id: str, filename: str, content: bytes) -> dict:
    """Saves a user-supplied video file (e.g. their own rebuttal/commentary
    recording) to be spliced into the compiled timeline between claim
    clips. Stored per-check alongside the rest of that check's editor
    artifacts."""
    upload_id = str(uuid.uuid4())
    suffix = Path(filename).suffix or ".mp4"
    uploads_dir = settings.data_dir / "reel_checks" / check_id / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    video_path = uploads_dir / f"{upload_id}{suffix}"
    video_path.write_bytes(content)

    duration = _probe_duration(video_path)
    db.execute(
        "INSERT INTO editor_uploads (id, check_id, filename, video_path, duration_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (upload_id, check_id, filename, str(video_path), duration),
    )
    return {
        "id": upload_id, "check_id": check_id, "filename": filename,
        "duration_seconds": duration,
    }


def list_uploads(check_id: str) -> list[dict]:
    rows = db.fetch_all(
        "SELECT id, filename, duration_seconds, created_at FROM editor_uploads "
        "WHERE check_id=? ORDER BY created_at",
        (check_id,),
    )
    return [dict(r) for r in rows]
