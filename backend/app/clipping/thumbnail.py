from pathlib import Path

from app.core.config import settings
from app.core.proc import run_checked


def generate_thumbnail(clip_path: Path, output_path: Path, offset_seconds: float = 2.0) -> Path:
    """Grabs a single frame a couple seconds into the clip, avoiding the
    black/transition frame often present at offset 0 right at a cut boundary."""
    run_checked([
        settings.ffmpeg_bin, "-loglevel", "error",
        "-ss", f"{offset_seconds:.3f}",
        "-i", str(clip_path),
        "-frames:v", "1",
        "-q:v", "3",
        "-y", str(output_path),
    ])
    return output_path
