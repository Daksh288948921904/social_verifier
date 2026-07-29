import asyncio
import logging
import queue
import uuid
from pathlib import Path

from app.clipping.cutter import cut_clip
from app.clipping.thumbnail import generate_thumbnail
from app.core import db
from app.core.config import settings
from app.events.bus import bus
from app.ingest.capture import CaptureSupervisor
from app.ingest.segment_index import SegmentRecord
from app.ingest.source_resolver import is_youtube_url, resolve_source
from app.rag import vector_store
from app.rag.embeddings import embed_text
from app.segmentation.boundary_detector import extract_cuts
from app.segmentation.state_machine import SegmentationStateMachine
from app.transcription.audio_preprocess import apply_dsp, concat_wavs
from app.transcription.groq_whisper import transcribe_chunk
from app.transcription.rolling_buffer import RollingTranscriptBuffer
from app.transcription.vad_chunker import has_speech

RAG_TOP_K = 5

logger = logging.getLogger(__name__)

_SENTINEL = object()


class SessionRunner:
    """Owns the full async task graph for one live-capture session: the
    ffmpeg capture subprocesses, the transcription worker, the segmentation
    (boundary-detection) loop, and the clip-cutting worker. Start/stop is
    just spawning/cancelling this object's tasks and killing its
    subprocesses."""

    def __init__(self, session_id: str, url: str):
        self.session_id = session_id
        self.url = url
        self.session_dir = settings.data_dir / "sessions" / session_id

        source_type = "youtube_live" if is_youtube_url(url) else "direct"
        db.execute(
            "INSERT INTO sessions (id, url, source_type, status) VALUES (?, ?, ?, ?)",
            (session_id, url, source_type, "starting"),
        )

        self.source = resolve_source(url)
        self.capture = CaptureSupervisor(self.session_dir, self.source)
        self.buffer = RollingTranscriptBuffer()
        self.state = SegmentationStateMachine()

        self._audio_queue: queue.Queue = queue.Queue()
        self._batch_chunks: list[tuple[Path, SegmentRecord]] = []
        self._batch_duration = 0.0
        self._transcription_task: asyncio.Task | None = None
        self._stopped = False

    def _on_segment(self, kind: str, path: Path, record: SegmentRecord) -> None:
        if kind == "audio":
            self._audio_queue.put((path, record))

    def start(self) -> None:
        db.execute(
            "UPDATE sessions SET status='capturing', started_at=datetime('now') WHERE id=?",
            (self.session_id,),
        )
        self.capture.start(
            on_segment=self._on_segment,
            on_fatal_error=self._on_capture_fatal_error,
            on_complete=self._on_capture_complete,
        )
        self._transcription_task = asyncio.create_task(self._transcription_worker())
        bus.publish(self.session_id, {"type": "status", "status": "capturing"})

    def _on_capture_complete(self) -> None:
        """Runs on the capture supervisor's watcher thread once it detects
        that a finite source's own known duration has been fully captured --
        a normal, successful end of session (e.g. a VOD played to its end),
        not a failure."""
        if self._stopped:
            return
        self._stopped = True
        db.execute(
            "UPDATE sessions SET status='stopped', ended_at=datetime('now') WHERE id=?",
            (self.session_id,),
        )
        bus.publish(self.session_id, {"type": "status", "status": "stopped"})
        self._audio_queue.put(_SENTINEL)
        active_sessions.pop(self.session_id, None)

    def _on_capture_fatal_error(self, message: str) -> None:
        """Runs on the capture supervisor's watcher thread (not the event
        loop) once it has exhausted its restart retries. db.execute and
        bus.publish are both documented as thread-safe for exactly this."""
        if self._stopped:
            return
        self._stopped = True
        db.execute(
            "UPDATE sessions SET status='error', ended_at=datetime('now') WHERE id=?",
            (self.session_id,),
        )
        bus.publish(self.session_id, {"type": "error", "message": message})
        bus.publish(self.session_id, {"type": "status", "status": "error"})
        self._audio_queue.put(_SENTINEL)
        active_sessions.pop(self.session_id, None)

    async def stop(self) -> None:
        self._stopped = True
        await asyncio.to_thread(self.capture.stop)
        self._audio_queue.put(_SENTINEL)
        if self._transcription_task:
            await self._transcription_task
        db.execute(
            "UPDATE sessions SET status='stopped', ended_at=datetime('now') WHERE id=?",
            (self.session_id,),
        )
        bus.publish(self.session_id, {"type": "status", "status": "stopped"})

    async def _transcription_worker(self) -> None:
        """Accumulates incoming audio chunks until settings.batch_window_seconds
        worth has arrived, then runs DSP + transcription + cut-extraction once
        over the whole batch instead of once per small capture chunk -- far
        fewer, far cheaper Groq calls, and the segmentation LLM gets a full
        ~10-minute block of context per call instead of a few seconds at a
        time, which gives it enough to actually judge where a story ends."""
        while True:
            item = await asyncio.to_thread(self._audio_queue.get)
            is_sentinel = item is _SENTINEL
            if not is_sentinel:
                path, record = item
                self._batch_chunks.append((path, record))
                self._batch_duration += record.duration

            should_flush = is_sentinel or self._batch_duration >= settings.batch_window_seconds
            if should_flush and self._batch_chunks:
                try:
                    await self._process_batch()
                except Exception:
                    logger.exception("Failed processing transcript batch")
                    bus.publish(self.session_id, {
                        "type": "error",
                        "message": "Failed to process a transcript batch",
                    })
                finally:
                    self._batch_chunks = []
                    self._batch_duration = 0.0

            if is_sentinel:
                break

    async def _process_batch(self) -> None:
        chunks = self._batch_chunks
        batch_start_offset = chunks[0][1].start_offset
        raw_paths = [path for path, _ in chunks]

        batch_dir = self.session_dir / "audio_batches"
        batch_dir.mkdir(parents=True, exist_ok=True)
        batch_id = f"batch_{int(batch_start_offset):08d}"
        raw_batch_path = batch_dir / f"{batch_id}_raw.wav"
        processed_batch_path = batch_dir / f"{batch_id}_dsp.wav"

        await asyncio.to_thread(concat_wavs, raw_paths, raw_batch_path)

        # Speech-gate on the RAW batch, before DSP: loudnorm boosts near-silent
        # room tone up to a normal-sounding level (observed live: -50dB -> -24dB),
        # which masks the silence signal a post-DSP check would otherwise catch
        # and lets Whisper hallucinate plausible-but-fake text over it.
        if not await asyncio.to_thread(has_speech, raw_batch_path):
            return

        await asyncio.to_thread(apply_dsp, raw_batch_path, processed_batch_path)

        segments = await asyncio.to_thread(transcribe_chunk, processed_batch_path, batch_start_offset)
        if not segments:
            return

        self.buffer.add_chunk_segments(segments)
        for seg in segments:
            db.execute(
                "INSERT INTO transcript_segments (session_id, absolute_start, absolute_end, text) "
                "VALUES (?, ?, ?, ?)",
                (self.session_id, seg.absolute_start, seg.absolute_end, seg.text),
            )
            bus.publish(self.session_id, {
                "type": "transcript_tick",
                "text": seg.text,
                "start": seg.absolute_start,
                "end": seg.absolute_end,
            })

        await self._check_boundaries()

    async def _check_boundaries(self) -> None:
        window_segments = self.buffer.segments_from(self.state.window_start_seconds())
        window_text = self.buffer.as_text(window_segments)
        if not window_text:
            return

        previously_covered = await self._retrieve_prior_coverage(window_text)
        try:
            cuts = await asyncio.to_thread(extract_cuts, window_text, previously_covered)
        except Exception:
            logger.exception("Cut extraction call failed")
            return

        for pending in self.state.apply(cuts):
            bus.publish(self.session_id, {
                "type": "segment_boundary_detected",
                "title": pending.title,
                "summary": pending.summary,
                "start": pending.start_seconds,
                "end": pending.end_seconds,
            })
            await self._cut_clip(pending)

    async def _retrieve_prior_coverage(self, window_text: str) -> list[str]:
        """RAG step: embeds the current transcript window and looks up the
        most similar clips already cut earlier in this session, so the next
        extract_cuts() call knows what's already been published instead of
        working from the transcript alone."""
        try:
            query_embedding = await asyncio.to_thread(embed_text, window_text)
            hits = await asyncio.to_thread(vector_store.search, self.session_id, query_embedding, RAG_TOP_K)
        except Exception:
            logger.exception("Prior-coverage retrieval failed; continuing without it")
            return []
        return [text for _clip_id, _score, text in hits]

    async def _cut_clip(self, pending) -> None:
        clip_id = str(uuid.uuid4())
        clips_dir = self.session_dir / "clips"
        video_path = clips_dir / f"{clip_id}.mp4"
        thumb_path = clips_dir / f"{clip_id}_thumb.jpg"

        try:
            await asyncio.to_thread(
                cut_clip,
                self.session_dir / "segments",
                self.capture.index,
                pending.start_seconds,
                pending.end_seconds,
                video_path,
            )
            await asyncio.to_thread(generate_thumbnail, video_path, thumb_path)
        except Exception:
            logger.exception("Failed to cut clip for pending segment %r", pending)
            bus.publish(self.session_id, {"type": "error", "message": f"Failed to cut clip: {pending.title}"})
            return

        db.execute(
            "INSERT INTO clips (id, session_id, title, summary, start_seconds, end_seconds, "
            "video_path, thumbnail_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                clip_id, self.session_id, pending.title, pending.summary,
                pending.start_seconds, pending.end_seconds, str(video_path), str(thumb_path),
            ),
        )

        clip_text = f"{pending.title}\n{pending.summary}"
        try:
            embedding = await asyncio.to_thread(embed_text, clip_text)
            await asyncio.to_thread(vector_store.add_clip, clip_id, self.session_id, embedding, clip_text)
        except Exception:
            logger.exception("Failed to store clip embedding for %s; clip itself was still saved", clip_id)

        bus.publish(self.session_id, {
            "type": "clip_ready",
            "clip_id": clip_id,
            "title": pending.title,
            "video_url": f"/api/clips/{clip_id}/video",
            "thumbnail_url": f"/api/clips/{clip_id}/thumbnail",
        })


# Registry of live session runners, keyed by session_id.
active_sessions: dict[str, SessionRunner] = {}
