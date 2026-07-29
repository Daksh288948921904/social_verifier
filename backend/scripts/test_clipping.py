"""Standalone test for step 4: cut a clip out of already-archived video
segments (from scripts/test_capture.py), remux to .mp4, and generate a
thumbnail. Verifies the concat+trim strategy produces a playable output.

Usage:
    python scripts/test_clipping.py [start_seconds] [end_seconds]
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clipping.cutter import cut_clip
from app.clipping.thumbnail import generate_thumbnail
from app.core.config import settings
from app.ingest.segment_index import SegmentIndex

SESSION_DIR = Path(__file__).resolve().parents[1] / "data" / "sessions" / "test_capture"


def probe(path: Path) -> str:
    result = subprocess.run(
        [
            settings.ffprobe_bin, "-v", "error",
            "-show_entries", "format=duration",
            "-show_entries", "stream=codec_type,codec_name",
            "-of", "default=noprint_wrappers=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def main():
    index = SegmentIndex(SESSION_DIR, name="segments_index.json")
    if not index.records:
        print(f"No video segment index at {SESSION_DIR} -- run scripts/test_capture.py first.")
        sys.exit(1)

    total_duration = index.records[-1].end_offset
    start = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    end = float(sys.argv[2]) if len(sys.argv) > 2 else min(25.0, total_duration - 1)

    clips_dir = SESSION_DIR / "clips"
    output_path = clips_dir / "test_clip.mp4"
    thumb_path = clips_dir / "test_clip_thumb.jpg"

    print(f"Cutting clip [{start}s, {end}s] from {len(index.records)} archived segments "
          f"(total archive: {total_duration:.1f}s)")
    cut_clip(SESSION_DIR / "segments", index, start, end, output_path)
    generate_thumbnail(output_path, thumb_path, offset_seconds=min(2.0, end - start - 0.1))

    print("\n--- Cut clip info ---")
    print(probe(output_path))

    if not output_path.exists() or output_path.stat().st_size == 0:
        print("FAIL: clip file missing or empty")
        sys.exit(1)
    if not thumb_path.exists() or thumb_path.stat().st_size == 0:
        print("FAIL: thumbnail missing or empty")
        sys.exit(1)

    print(f"\nPASS: clip written to {output_path} ({output_path.stat().st_size} bytes)")
    print(f"      thumbnail written to {thumb_path} ({thumb_path.stat().st_size} bytes)")
    print(f"\nInspect with: open '{output_path}'")


if __name__ == "__main__":
    main()
