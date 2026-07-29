import logging
from dataclasses import dataclass

from app.segmentation.boundary_detector import ProposedCut

logger = logging.getLogger(__name__)


def _ts_to_seconds(ts: str) -> float:
    # Tolerate "SS", "MM:SS", or "HH:MM:SS" -- the segmentation LLM doesn't
    # always include the hour field, especially early in a session.
    parts = [float(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s


@dataclass
class PendingClip:
    start_seconds: float
    end_seconds: float
    title: str
    summary: str


class SegmentationStateMachine:
    """Tracks which prefix of the session's transcript has already been
    turned into clips.

    Each batch window's extract_cuts() call only returns stories that fully
    concluded within that block. last_confirmed_boundary_ts is the end of
    the last cut applied, fed back in as the start of the next block's
    transcript window so a story still in progress at the end of one batch
    carries forward into the next instead of being cut off mid-story.
    """

    def __init__(self):
        self.last_confirmed_boundary_ts: str | None = None

    def window_start_seconds(self) -> float:
        if not self.last_confirmed_boundary_ts:
            return 0.0
        return _ts_to_seconds(self.last_confirmed_boundary_ts)

    def apply(self, cuts: list[ProposedCut]) -> list[PendingClip]:
        pending: list[PendingClip] = []
        for cut in cuts:
            try:
                start_seconds = _ts_to_seconds(cut.start_timestamp)
                end_seconds = _ts_to_seconds(cut.end_timestamp)
            except (ValueError, AttributeError):
                logger.warning("Skipping cut with unparseable timestamps: %r", cut)
                continue
            pending.append(PendingClip(start_seconds, end_seconds, cut.title, cut.summary))
            self.last_confirmed_boundary_ts = cut.end_timestamp
        return pending
