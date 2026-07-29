from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.groq_pool import next_client


@dataclass
class TranscriptSegment:
    absolute_start: float
    absolute_end: float
    text: str


def transcribe_chunk(audio_path: Path, chunk_start_offset: float) -> list[TranscriptSegment]:
    """Sends one (post-DSP) audio chunk to Groq Whisper and converts the
    chunk-relative segment timestamps it returns into stream-absolute ones by
    adding chunk_start_offset."""
    client = next_client()
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            file=(audio_path.name, f.read()),
            model=settings.whisper_model,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = []
    for seg in getattr(response, "segments", None) or []:
        seg_start = seg["start"] if isinstance(seg, dict) else seg.start
        seg_end = seg["end"] if isinstance(seg, dict) else seg.end
        seg_text = seg["text"] if isinstance(seg, dict) else seg.text
        segments.append(
            TranscriptSegment(
                absolute_start=chunk_start_offset + seg_start,
                absolute_end=chunk_start_offset + seg_end,
                text=seg_text.strip(),
            )
        )
    if not segments and getattr(response, "text", "").strip():
        # Fall back to whole-chunk text if the API didn't return segment-level
        # timestamps for some reason.
        segments.append(
            TranscriptSegment(
                absolute_start=chunk_start_offset,
                absolute_end=chunk_start_offset + settings.chunk_seconds,
                text=response.text.strip(),
            )
        )
    return segments
