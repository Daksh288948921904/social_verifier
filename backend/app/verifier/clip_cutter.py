import subprocess
from pathlib import Path

from app.core.config import settings


def cut_claim_clip(source_path: Path, start_seconds: float, end_seconds: float, output_path: Path) -> Path:
    """Cuts and re-encodes (rather than stream-copying) a short segment of
    the downloaded source video. Re-encoding costs a bit more time but
    gives frame-accurate boundaries at the exact matched quote timing --
    stream-copy can only snap to the nearest keyframe, which would undercut
    the precision clip_match already went to the trouble of computing.
    -ss before -i seeks close to the target first (fast); the following
    re-encode is still decoded from there, giving an accurate cut."""
    duration = max(0.1, end_seconds - start_seconds)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            settings.ffmpeg_bin, "-loglevel", "error", "-y",
            "-ss", f"{max(0.0, start_seconds):.3f}",
            "-i", str(source_path),
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-c:a", "aac",
            str(output_path),
        ],
        check=True, capture_output=True, text=True,
    )
    return output_path
