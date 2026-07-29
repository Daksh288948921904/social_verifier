"""Standalone test for step 2: DSP preprocessing + VAD + Groq Whisper
transcription, run against audio chunks already captured in step 1
(backend/data/sessions/test_capture/audio).

Usage:
    python scripts/test_transcription.py

If GROQ_API_KEY is unset or still the placeholder, the Groq Whisper calls
are skipped and only the DSP/VAD stages are exercised (still validates the
ffmpeg filter chain and webrtcvad wiring end-to-end).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.transcription.audio_preprocess import apply_dsp
from app.transcription.groq_whisper import transcribe_chunk
from app.transcription.rolling_buffer import RollingTranscriptBuffer
from app.transcription.vad_chunker import analyze, has_speech, speech_ratio

SESSION_DIR = Path(__file__).resolve().parents[1] / "data" / "sessions" / "test_capture"
AUDIO_DIR = SESSION_DIR / "audio"
PROCESSED_DIR = SESSION_DIR / "audio_processed"


def groq_key_available() -> bool:
    return bool(settings.groq_api_key) and "placeholder" not in settings.groq_api_key


def main():
    audio_index_path = SESSION_DIR / "audio_index.json"
    if not audio_index_path.exists():
        print(f"No audio index at {audio_index_path} -- run scripts/test_capture.py first.")
        sys.exit(1)

    records = json.loads(audio_index_path.read_text())
    if not records:
        print("Audio index is empty -- run scripts/test_capture.py first.")
        sys.exit(1)

    PROCESSED_DIR.mkdir(exist_ok=True)
    has_key = groq_key_available()
    if not has_key:
        print("GROQ_API_KEY not set (or still the placeholder) -- skipping Whisper calls,")
        print("validating DSP + VAD stages only.\n")

    buffer_raw = RollingTranscriptBuffer()
    buffer_dsp = RollingTranscriptBuffer()

    for rec in records:
        raw_path = AUDIO_DIR / rec["filename"]
        processed_path = PROCESSED_DIR / rec["filename"]
        start_offset = rec["start_offset"]

        raw_ratio = speech_ratio(analyze(raw_path))
        apply_dsp(raw_path, processed_path)
        dsp_ratio = speech_ratio(analyze(processed_path))

        print(
            f"{rec['filename']}  start={start_offset:.2f}s  "
            f"speech_ratio raw={raw_ratio:.2f} dsp={dsp_ratio:.2f}  "
            f"speech_present={has_speech(processed_path)}"
        )

        if has_key:
            raw_segments = transcribe_chunk(raw_path, start_offset)
            dsp_segments = transcribe_chunk(processed_path, start_offset)
            buffer_raw.add_chunk_segments(raw_segments)
            buffer_dsp.add_chunk_segments(dsp_segments)

    if has_key:
        print("\n--- Transcript WITHOUT DSP preprocessing ---")
        print(buffer_raw.as_text() or "(empty)")
        print("\n--- Transcript WITH DSP preprocessing ---")
        print(buffer_dsp.as_text() or "(empty)")
    else:
        print("\nPASS: DSP + VAD pipeline runs end-to-end. Set a real GROQ_API_KEY in")
        print(".env and re-run to also validate Whisper transcription quality.")


if __name__ == "__main__":
    main()
