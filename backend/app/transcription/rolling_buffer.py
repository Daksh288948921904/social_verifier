from app.transcription.groq_whisper import TranscriptSegment


class RollingTranscriptBuffer:
    """Ordered, deduplicated transcript for one capture session.

    Chunk transcriptions can arrive slightly out of order (Groq call
    latencies vary), and adjacent chunks may overlap slightly (VAD-aligned
    or not), so segments are sorted by start time and any segment that
    starts before the current buffer's end is dropped as a duplicate rather
    than appended twice.
    """

    def __init__(self):
        self.segments: list[TranscriptSegment] = []

    def add_chunk_segments(self, new_segments: list[TranscriptSegment]) -> None:
        for seg in sorted(new_segments, key=lambda s: s.absolute_start):
            if self.segments and seg.absolute_start < self.segments[-1].absolute_end:
                continue
            self.segments.append(seg)

    def segments_from(self, start_seconds: float) -> list[TranscriptSegment]:
        """Everything from start_seconds onward -- used to hand the LLM the
        still-open tail of a previous batch plus all of the newly
        transcribed batch, so a story isn't cut off mid-story at a batch
        boundary."""
        return [s for s in self.segments if s.absolute_end > start_seconds]

    def as_text(self, segments: list[TranscriptSegment] | None = None) -> str:
        segments = segments if segments is not None else self.segments

        def fmt_ts(t: float) -> str:
            h, rem = divmod(int(t), 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"

        return "\n".join(f"[{fmt_ts(s.absolute_start)}] {s.text}" for s in segments)
