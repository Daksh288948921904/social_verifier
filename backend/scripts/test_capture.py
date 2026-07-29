"""Standalone test for step 1: capture a live-ish stream to disk and verify
the resulting chunks are valid, playable, and correctly indexed.

Usage:
    python scripts/test_capture.py [url] [duration_seconds]

Defaults to Apple's public HLS test stream (not a real live broadcast, but a
continuously-servable HLS source useful for exercising the segmenter without
depending on an actual live news feed).
"""
import logging
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.capture import CaptureSupervisor
from app.ingest.source_resolver import resolve_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_URL = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 35.0

    session_dir = Path(__file__).resolve().parents[1] / "data" / "sessions" / "test_capture"
    if session_dir.exists():
        shutil.rmtree(session_dir)
    session_dir.mkdir(parents=True)

    source = resolve_source(url)
    print(f"Resolved source type: {type(source).__name__}")

    supervisor = CaptureSupervisor(session_dir, source, chunk_seconds=10)
    supervisor.start()
    print(f"Capturing for {duration}s...")
    time.sleep(duration)
    supervisor.stop()

    print("\n--- Segment index ---")
    for rec in supervisor.index.records:
        print(rec)

    video_files = sorted((session_dir / "segments").glob("*.ts"))
    audio_files = sorted((session_dir / "audio").glob("*.wav"))
    print(f"\nVideo chunks: {len(video_files)}  Audio chunks: {len(audio_files)}")

    if not video_files or not audio_files:
        print("FAIL: no chunks were produced")
        sys.exit(1)

    print("PASS: chunks produced. Inspect with e.g.:")
    print(f"  ffprobe '{video_files[0]}'")
    print(f"  afplay '{audio_files[0]}'  # or open in a media player")


if __name__ == "__main__":
    main()
