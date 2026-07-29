import logging
import subprocess
import threading
import time
from pathlib import Path

from app.core.config import settings
from app.ingest.segment_index import SegmentIndex
from app.ingest.source_resolver import StreamSource

logger = logging.getLogger(__name__)


class CaptureSupervisor:
    """Owns the ffmpeg subprocesses that continuously archive a live stream
    to disk as fixed-length video (.ts) and raw audio (.wav) chunks.

    Supervises both processes: if either dies (network hiccup, expired
    resolved URL, source outage), it re-resolves the source (if needed) and
    restarts capture under a new run_id, so the segment index can track the
    discontinuity instead of silently corrupting offsets.

    Restarts back off exponentially and are capped at max_consecutive_failures:
    a source that is genuinely gone (stream ended, format permanently
    unresolvable) must not keep the supervisor retrying forever. The failure
    streak resets once a run stays up longer than STABLE_RUN_SECONDS, so a
    single flaky restart doesn't count against a source that's otherwise fine.
    """

    STABLE_RUN_SECONDS = 60.0
    MAX_BACKOFF_SECONDS = 60.0

    def __init__(
        self,
        session_dir: Path,
        source: StreamSource,
        chunk_seconds: int | None = None,
        max_consecutive_failures: int = 5,
    ):
        self.session_dir = session_dir
        self.source = source
        self.chunk_seconds = chunk_seconds or settings.chunk_seconds
        self.max_consecutive_failures = max_consecutive_failures

        self.segments_dir = session_dir / "segments"
        self.audio_dir = session_dir / "audio"
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.index = SegmentIndex(session_dir, name="segments_index.json")
        self.audio_index = SegmentIndex(session_dir, name="audio_index.json")
        self._indexed_video: set[str] = set()
        self._indexed_audio: set[str] = set()

        self._video_proc: subprocess.Popen | None = None
        self._audio_proc: subprocess.Popen | None = None
        self._run_id = 0
        self._run_spawned_at = 0.0
        self._consecutive_failures = 0
        self._stop_event = threading.Event()
        self._watcher_thread: threading.Thread | None = None
        self._on_segment = None  # optional callback(kind: str, path: Path, record: SegmentRecord)
        self._on_fatal_error = None  # optional callback(message: str), fired once retries are exhausted
        self._on_complete = None  # optional callback(), fired when a finite source is fully captured

    def start(self, on_segment=None, on_fatal_error=None, on_complete=None) -> None:
        self._on_segment = on_segment
        self._on_fatal_error = on_fatal_error
        self._on_complete = on_complete
        self._stop_event.clear()
        self._spawn(self._run_id)
        self._watcher_thread = threading.Thread(target=self._supervise_loop, daemon=True)
        self._watcher_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for proc in (self._video_proc, self._audio_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if self._watcher_thread:
            self._watcher_thread.join(timeout=5)
        # ffmpeg has exited now, so every written file (including the last one
        # per process) is complete and safe to finalize into the index.
        self._finalize_new_segments(include_newest=True)

    def _spawn(self, run_id: int) -> None:
        self._run_spawned_at = time.monotonic()
        input_url = self.source.get_input_url()
        video_pattern = str(self.segments_dir / f"run{run_id}_seg_%08d.ts")
        audio_pattern = str(self.audio_dir / f"run{run_id}_aud_%08d.wav")

        # Restarting a finite source (a VOD, or a broadcast that's already
        # ended) re-resolves to a URL that plays from t=0 again -- without
        # seeking, every restart would re-capture the same opening minutes
        # forever while the segment index's cursor keeps counting forward,
        # so the session would never reach (or even notice) the real end.
        # A genuinely live source's re-resolved URL has no fixed timeline to
        # seek into, so this only applies when total_duration_seconds is known.
        video_seek: list[str] = []
        audio_seek: list[str] = []
        if run_id > 0 and self.source.total_duration_seconds is not None:
            video_seek = ["-ss", f"{self.index.cursor_offset:.3f}"]
            audio_seek = ["-ss", f"{self.audio_index.cursor_offset:.3f}"]

        video_cmd = [
            settings.ffmpeg_bin,
            "-loglevel", "warning",
            *video_seek,
            "-i", input_url,
            "-c", "copy",
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-f", "segment",
            "-segment_time", str(self.chunk_seconds),
            "-segment_format", "mpegts",
            "-reset_timestamps", "0",
            video_pattern,
        ]
        audio_cmd = [
            settings.ffmpeg_bin,
            "-loglevel", "warning",
            *audio_seek,
            "-i", input_url,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            "-f", "segment",
            "-segment_time", str(self.chunk_seconds),
            "-reset_timestamps", "0",
            audio_pattern,
        ]

        logger.info("Starting capture run %d for %s", run_id, input_url)
        self._video_proc = subprocess.Popen(
            video_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
        )
        self._audio_proc = subprocess.Popen(
            audio_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
        )
        threading.Thread(
            target=self._drain_stderr, args=(self._video_proc, "video"), daemon=True
        ).start()
        threading.Thread(
            target=self._drain_stderr, args=(self._audio_proc, "audio"), daemon=True
        ).start()

    def _drain_stderr(self, proc: subprocess.Popen, label: str) -> None:
        if not proc.stderr:
            return
        for line in proc.stderr:
            line = line.strip()
            if line:
                logger.warning("[ffmpeg:%s] %s", label, line)

    def _finalize_new_segments(self, include_newest: bool = False) -> None:
        self._finalize_dir(
            self.segments_dir, "*.ts", self.index, self._indexed_video, "video", include_newest
        )
        self._finalize_dir(
            self.audio_dir, "*.wav", self.audio_index, self._indexed_audio, "audio", include_newest
        )

    def _finalize_dir(
        self,
        directory: Path,
        pattern: str,
        index: SegmentIndex,
        indexed_set: set[str],
        kind: str,
        include_newest: bool,
    ) -> None:
        files = sorted(directory.glob(pattern))
        if not files:
            return
        # The highest-numbered file is still being actively written by ffmpeg
        # (unless the process has already exited), so skip it until then.
        candidates = files if include_newest else files[:-1]
        for f in candidates:
            if f.name in indexed_set:
                continue
            record = index.record_segment(f, self._run_id)
            indexed_set.add(f.name)
            if self._on_segment:
                try:
                    self._on_segment(kind, f, record)
                except Exception:
                    logger.exception("on_segment callback failed for %s", f)

    def _supervise_loop(self, poll_interval: float = 2.0, backoff_seconds: float = 5.0) -> None:
        while not self._stop_event.is_set():
            time.sleep(poll_interval)
            if self._stop_event.is_set():
                break
            try:
                self._supervise_tick(backoff_seconds)
            except Exception:
                # This thread has no other supervisor -- an unhandled
                # exception anywhere in the tick (as happened when a
                # near-empty segment made ffprobe return "N/A" and crashed
                # an unguarded float() call) would otherwise kill this
                # thread silently, leaving the session stuck at
                # status='capturing' forever with no restart, no error, and
                # no visibility. Treat it the same as exhausting retries.
                message = "Capture supervisor hit an unexpected error; giving up on this source."
                logger.exception(message)
                self._stop_event.set()
                if self._on_fatal_error:
                    try:
                        self._on_fatal_error(message)
                    except Exception:
                        logger.exception("on_fatal_error callback failed")

    def _supervise_tick(self, backoff_seconds: float) -> None:
        """One poll-interval's worth of supervision: check whether the
        current run died, and if so, either detect clean completion, give
        up after too many consecutive failures, or restart with backoff.
        Runs inside the try/except in _supervise_loop, so raising here (as
        opposed to using break/continue, which only make sense inside the
        loop that used to contain this code) is what triggers the
        give-up-and-report-it fallback for any unexpected error."""
        self._finalize_new_segments()
        video_dead = self._video_proc is not None and self._video_proc.poll() is not None
        audio_dead = self._audio_proc is not None and self._audio_proc.poll() is not None
        if not (video_dead or audio_dead):
            return
        if self._stop_event.is_set():
            # stop() itself terminated these processes; not a real failure.
            return

        logger.warning(
            "Capture run %d died (video_dead=%s audio_dead=%s); restarting",
            self._run_id, video_dead, audio_dead,
        )
        for proc in (self._video_proc, self._audio_proc):
            if proc and proc.poll() is None:
                proc.terminate()
        self._finalize_new_segments(include_newest=True)

        total = self.source.total_duration_seconds
        captured = min(self.index.cursor_offset, self.audio_index.cursor_offset)
        if total is not None and captured >= total - 1.0:
            logger.info(
                "Capture run %d reached the end of a %.1fs source (captured %.1fs); "
                "stopping cleanly instead of restarting.",
                self._run_id, total, captured,
            )
            self._stop_event.set()
            if self._on_complete:
                try:
                    self._on_complete()
                except Exception:
                    logger.exception("on_complete callback failed")
            return

        if time.monotonic() - self._run_spawned_at >= self.STABLE_RUN_SECONDS:
            self._consecutive_failures = 0
        self._consecutive_failures += 1

        if self._consecutive_failures >= self.max_consecutive_failures:
            message = (
                f"Capture failed {self._consecutive_failures} times in a row; "
                "giving up on this source."
            )
            logger.error(message)
            self._stop_event.set()
            if self._on_fatal_error:
                try:
                    self._on_fatal_error(message)
                except Exception:
                    logger.exception("on_fatal_error callback failed")
            return

        delay = min(backoff_seconds * (2 ** (self._consecutive_failures - 1)), self.MAX_BACKOFF_SECONDS)
        time.sleep(delay)
        if self._stop_event.is_set():
            return
        self._run_id += 1
        try:
            self._spawn(self._run_id)
        except Exception:
            logger.exception("Failed to restart capture run %d", self._run_id)
                # _video_proc/_audio_proc still point at the previous (dead)
                # processes, so the poll() check above will catch this as
                # another death on the next iteration and retry/back off again.
