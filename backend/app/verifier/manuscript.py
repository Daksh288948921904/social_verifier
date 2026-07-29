from pathlib import Path

from app.transcription.audio_preprocess import apply_dsp
from app.transcription.groq_whisper import TranscriptSegment, transcribe_chunk


def _fmt_ts(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_manuscript(raw_audio: Path, processed_audio: Path) -> tuple[str, list[TranscriptSegment]]:
    """DSP + a single Groq Whisper call over the whole clip (reels are
    short -- no need for the live-pipeline's batching), producing a
    timestamped manuscript so later claim quotes can be tied back to an
    exact moment in the source clip. Returns the raw segments alongside the
    formatted text so callers can match a claim's quote back to precise
    (start, end) boundaries for cutting a downloadable clip."""
    apply_dsp(raw_audio, processed_audio)
    segments = transcribe_chunk(processed_audio, chunk_start_offset=0.0)
    if not segments:
        return "", []
    manuscript = "\n".join(f"[{_fmt_ts(s.absolute_start)}] {s.text}" for s in segments)
    return manuscript, segments
