import re
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import webrtcvad

from app.core.config import settings

FRAME_MS = 30
SAMPLE_RATE = 16000

# Whisper hallucinates plausible-sounding but fake text on near-silent audio
# (observed live: a -50dB mean-volume chunk of studio room tone transcribed
# as "How are you?" with no_speech_prob=0 -- the model's own confidence
# signals don't catch this, so a direct loudness gate is the reliable check).
MIN_MEAN_VOLUME_DB = -38.0


@dataclass
class VadFrame:
    offset: float  # seconds from start of the audio file
    duration: float
    is_speech: bool


def _read_pcm16_mono(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1 or wf.getframerate() != SAMPLE_RATE:
            raise ValueError(
                f"{path} must be 16-bit mono PCM at {SAMPLE_RATE}Hz "
                f"(got sampwidth={wf.getsampwidth()} ch={wf.getnchannels()} rate={wf.getframerate()})"
            )
        return wf.readframes(wf.getnframes())


def analyze(path: Path, aggressiveness: int = 2, frame_ms: int = FRAME_MS) -> list[VadFrame]:
    """Runs WebRTC VAD over a 16kHz mono PCM WAV file, returning per-frame
    speech/silence classification with absolute-in-file timestamps."""
    vad = webrtcvad.Vad(aggressiveness)
    audio_bytes = _read_pcm16_mono(path)

    bytes_per_frame = int(SAMPLE_RATE * (frame_ms / 1000.0) * 2)
    frames: list[VadFrame] = []
    offset = 0.0
    for start in range(0, len(audio_bytes) - bytes_per_frame + 1, bytes_per_frame):
        raw = audio_bytes[start : start + bytes_per_frame]
        is_speech = vad.is_speech(raw, SAMPLE_RATE)
        frames.append(VadFrame(offset=offset, duration=frame_ms / 1000.0, is_speech=is_speech))
        offset += frame_ms / 1000.0
    return frames


def speech_ratio(frames: list[VadFrame]) -> float:
    if not frames:
        return 0.0
    return sum(1 for f in frames if f.is_speech) / len(frames)


def mean_volume_db(path: Path) -> float:
    """Mean audio level in dBFS via ffmpeg's volumedetect filter. Cheap
    (single subprocess, no decode-to-Python), and a far more reliable
    silence/room-tone detector than VAD frame ratio or Whisper's own
    no_speech_prob for near-silent audio."""
    result = subprocess.run(
        [settings.ffmpeg_bin, "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r"mean_volume:\s*(-?\d+(\.\d+)?)\s*dB", result.stderr)
    if not match:
        return -100.0  # couldn't measure -- treat as silence, safer to skip
    return float(match.group(1))


def has_speech(
    path: Path,
    aggressiveness: int = 2,
    min_ratio: float = 0.02,
    min_volume_db: float = MIN_MEAN_VOLUME_DB,
) -> bool:
    """Whether a chunk contains enough voice-like energy to be worth
    transcribing. Chunks below the VAD ratio (silence, music beds, stingers)
    or below the loudness floor (room tone, near-silence Whisper tends to
    hallucinate over) are skipped to save Groq calls and avoid Whisper
    inventing plausible-sounding but fake dialogue."""
    if mean_volume_db(path) < min_volume_db:
        return False
    frames = analyze(path, aggressiveness)
    return speech_ratio(frames) >= min_ratio


def find_silence_split(
    path: Path,
    target_seconds: float,
    search_window: float = 2.0,
    aggressiveness: int = 2,
) -> float:
    """Finds the nearest silence gap to `target_seconds` within +/- search_window,
    for snapping a chunk boundary so speech isn't cut mid-word/sentence.
    Falls back to target_seconds unchanged if no silence gap is found nearby.
    """
    frames = analyze(path, aggressiveness)
    candidates = [
        f for f in frames
        if not f.is_speech and abs(f.offset - target_seconds) <= search_window
    ]
    if not candidates:
        return target_seconds
    best = min(candidates, key=lambda f: abs(f.offset - target_seconds))
    return best.offset
