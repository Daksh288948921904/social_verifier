import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
from app.ingest.segment_index import SegmentIndex


def _concat(segment_paths: list[Path], output_path: Path) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")
        list_path = f.name
    try:
        subprocess.run(
            [
                settings.ffmpeg_bin, "-loglevel", "error",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                "-y", str(output_path),
            ],
            check=True, capture_output=True, text=True,
        )
    finally:
        Path(list_path).unlink(missing_ok=True)
    return output_path


def _trim_and_remux(input_path: Path, start: float, end: float, output_path: Path) -> Path:
    subprocess.run(
        [
            settings.ffmpeg_bin, "-loglevel", "error",
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-i", str(input_path),
            "-c", "copy",
            "-y", str(output_path),
        ],
        check=True, capture_output=True, text=True,
    )
    return output_path


def cut_clip(
    segments_dir: Path,
    index: SegmentIndex,
    start_offset: float,
    end_offset: float,
    output_path: Path,
) -> Path:
    """Cuts a clip covering [start_offset, end_offset] (stream-absolute
    seconds) out of the archived .ts segments, via lossless concat + a
    stream-copy trim, then remuxes to .mp4 for browser playback.

    Cuts snap to the nearest keyframe (stream-copy limitation) -- accurate to
    within a GOP, not frame-exact. See plan Section 2 for the tradeoff.
    """
    overlapping = index.segments_overlapping(start_offset, end_offset)
    if not overlapping:
        raise ValueError(f"No archived segments overlap [{start_offset}, {end_offset}]")

    segment_paths = [segments_dir / r.filename for r in overlapping]
    joined_start = overlapping[0].start_offset

    with tempfile.TemporaryDirectory() as tmp:
        joined_path = Path(tmp) / "joined.ts"
        _concat(segment_paths, joined_path)

        relative_start = max(0.0, start_offset - joined_start)
        relative_end = end_offset - joined_start
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _trim_and_remux(joined_path, relative_start, relative_end, output_path)

    return output_path
