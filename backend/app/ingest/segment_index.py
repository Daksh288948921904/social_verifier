import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.config import settings


@dataclass
class SegmentRecord:
    index: int
    run_id: int
    filename: str
    start_offset: float
    end_offset: float
    duration: float


class SegmentIndex:
    """Tracks archived video segments for a capture session.

    This is a simple file-backed index (JSON) for standalone/offline use in
    early build steps. Step 5 swaps the storage for a SQLite `segments` table
    without changing this class's public interface.
    """

    def __init__(self, session_dir: Path, name: str = "segments_index.json"):
        self.session_dir = session_dir
        self.index_path = session_dir / name
        self.records: list[SegmentRecord] = []
        self._cursor_offset = 0.0
        if self.index_path.exists():
            self._load()

    def _load(self) -> None:
        data = json.loads(self.index_path.read_text())
        self.records = [SegmentRecord(**r) for r in data]
        if self.records:
            self._cursor_offset = self.records[-1].end_offset

    @property
    def cursor_offset(self) -> float:
        return self._cursor_offset

    def _save(self) -> None:
        self.index_path.write_text(
            json.dumps([asdict(r) for r in self.records], indent=2)
        )

    @staticmethod
    def probe_duration(path: Path) -> float:
        result = subprocess.run(
            [
                settings.ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # ffprobe prints "N/A" (not an empty string) for a zero-byte or
        # otherwise malformed file -- e.g. a segment whose ffmpeg process
        # died before writing any real data. That's a legitimate outcome
        # (an empty capture chunk), not a crash-worthy one.
        try:
            return float(result.stdout.strip() or 0.0)
        except ValueError:
            return 0.0

    def record_segment(self, path: Path, run_id: int) -> SegmentRecord:
        duration = self.probe_duration(path)
        record = SegmentRecord(
            index=len(self.records),
            run_id=run_id,
            filename=path.name,
            start_offset=self._cursor_offset,
            end_offset=self._cursor_offset + duration,
            duration=duration,
        )
        self.records.append(record)
        self._cursor_offset += duration
        self._save()
        return record

    def segments_overlapping(self, start: float, end: float) -> list[SegmentRecord]:
        return [r for r in self.records if r.end_offset > start and r.start_offset < end]
