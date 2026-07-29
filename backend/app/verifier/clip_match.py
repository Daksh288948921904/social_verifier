import difflib
import re
from dataclasses import replace

from app.transcription.groq_whisper import TranscriptSegment
from app.verifier.claims import ExtractedClaim

MAX_WINDOW = 5  # max consecutive segments considered as one quote match
MIN_MATCH_SCORE = 0.55
FALLBACK_CLIP_SECONDS = 8.0
PADDING_SECONDS = 0.3


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _ts_to_seconds(ts: str) -> float:
    try:
        parts = [float(p) for p in ts.split(":")]
    except ValueError:
        return 0.0
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s


def match_quote_to_segments(quote: str, approx_timestamp: str, segments: list[TranscriptSegment]) -> tuple[float, float]:
    """Finds the real Whisper segment boundaries backing a claim's quoted
    text, so a downloadable clip can be cut precisely instead of guessing a
    fixed-length window from the LLM's own (often approximate) reported
    timestamp. Quotes are extracted verbatim from manuscript lines (one
    line per segment), so an exact or near-exact match against one or a
    few consecutive segments is the common case; falls back to a short
    fixed window around the reported timestamp if nothing lines up well."""
    approx_seconds = _ts_to_seconds(approx_timestamp)
    normalized_quote = _normalize(quote)
    if not normalized_quote or not segments:
        return approx_seconds, approx_seconds + FALLBACK_CLIP_SECONDS

    best_score = 0.0
    best_range: tuple[float, float] | None = None
    for i in range(len(segments)):
        concatenated = ""
        for j in range(i, min(i + MAX_WINDOW, len(segments))):
            concatenated = f"{concatenated} {segments[j].text}".strip()
            score = _similarity(_normalize(concatenated), normalized_quote)
            if score > best_score:
                best_score = score
                best_range = (segments[i].absolute_start, segments[j].absolute_end)

    if best_range and best_score >= MIN_MATCH_SCORE:
        start, end = best_range
        return max(0.0, start - PADDING_SECONDS), end + PADDING_SECONDS

    return approx_seconds, approx_seconds + FALLBACK_CLIP_SECONDS


def attach_clip_times(claims: list[ExtractedClaim], segments: list[TranscriptSegment]) -> list[ExtractedClaim]:
    enriched = []
    for c in claims:
        start, end = match_quote_to_segments(c.quote, c.timestamp, segments)
        enriched.append(replace(c, start_seconds=start, end_seconds=end))
    return enriched
