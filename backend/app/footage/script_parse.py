import json
import logging
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.groq_pool import call_rotating

logger = logging.getLogger(__name__)

MAX_SCRIPT_CHARS = 60_000

# A line that's only a segment heading, e.g. "SEGMENT 3 —" or "Part 2:".
_MARKER_RE = re.compile(r"^\s*(segment|part|chapter|act|section)\s+[\w.]+\s*[—–:\-]*\s*$", re.IGNORECASE)

SYSTEM_PROMPT = """You are a researcher on a news/documentary production team. You are given a
broadcast script with numbered lines. Your job: split it into its segments and, for each segment,
plan which real footage should be found on YouTube to cover it on screen.

Segments:
- If the script marks segments explicitly (e.g. "SEGMENT 2 —", "PART 3", headings), follow those
  markers exactly. Any text before the first marker is its own opening segment.
- Otherwise split at natural topic changes, aiming for segments of roughly 20-80 lines.
- Segments must cover the script in order. Give each one's first line number ("start_line").

For each segment give:
- "title": 2-6 words naming what the segment is about.
- "summary": 1-2 sentences on what the segment says.
- "visual_needs": one sentence describing the footage an editor would want on screen for it
  (people, places, events, archival material, data visuals).
- "keywords": 3-6 YouTube search queries that would surface real footage for this segment. Make
  them specific and searchable -- named people, events, places, years, plus words like
  "footage", "speech", "archival", "news report", "documentary" where useful. Each keyword has
  "text" (the query) and "rationale" (which part of the segment it covers, in one short sentence).
  Do not repeat the same query across segments.

Respond with JSON only:
{"title": "<short title for the whole script>",
 "segments": [{"start_line": 1, "title": "...", "summary": "...", "visual_needs": "...",
               "keywords": [{"text": "...", "rationale": "..."}]}]}
"""


@dataclass
class ParsedSegment:
    title: str
    summary: str
    visual_needs: str
    script_excerpt: str
    keywords: list[dict] = field(default_factory=list)  # [{text, rationale}]


@dataclass
class ParsedScript:
    title: str
    segments: list[ParsedSegment]


def parse_script(script: str) -> ParsedScript:
    """Splits a script into segments with suggested search keywords. The LLM
    only returns each segment's *first line number*, never the text itself --
    the excerpts are sliced back out of the original script here, so a long
    script costs no extra output tokens and its wording can't be paraphrased
    or truncated along the way."""
    lines = [line.rstrip() for line in script[:MAX_SCRIPT_CHARS].splitlines()]
    # Drop pure separator lines (e.g. "· · ·") from the numbered view so they
    # don't waste tokens; their line numbers stay valid for slicing.
    numbered = "\n".join(
        f"{i + 1}: {line}" for i, line in enumerate(lines) if any(c.isalnum() for c in line)
    )

    response = call_rotating(lambda client: client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": numbered},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        reasoning_effort="low",
    ))
    data = json.loads(response.choices[0].message.content)

    raw_segments = [s for s in data.get("segments") or [] if isinstance(s, dict)]
    starts = []
    for s in raw_segments:
        try:
            starts.append(max(1, min(len(lines), int(s.get("start_line", 1)))))
        except (TypeError, ValueError):
            starts.append(1)
    # Guard against out-of-order line numbers so every segment's slice is valid.
    for i in range(1, len(starts)):
        starts[i] = max(starts[i], starts[i - 1])

    segments = []
    for i, s in enumerate(raw_segments):
        end = starts[i + 1] - 1 if i + 1 < len(starts) else len(lines)
        body = [line for line in lines[starts[i] - 1:end] if any(c.isalnum() for c in line)]
        # Marker lines are headings, not script -- and the LLM sometimes
        # starts a segment one line late, leaving the next segment's marker
        # dangling at the end of this one.
        while body and _MARKER_RE.match(body[0]):
            body.pop(0)
        while body and _MARKER_RE.match(body[-1]):
            body.pop()
        excerpt = "\n".join(body)
        keywords = [
            {"text": str(k.get("text", "")).strip(), "rationale": str(k.get("rationale", "")).strip()}
            for k in s.get("keywords") or [] if isinstance(k, dict) and str(k.get("text", "")).strip()
        ]
        segments.append(ParsedSegment(
            title=str(s.get("title") or f"Segment {i + 1}").strip(),
            summary=str(s.get("summary") or "").strip(),
            visual_needs=str(s.get("visual_needs") or "").strip(),
            script_excerpt=excerpt,
            keywords=keywords,
        ))

    if not segments:
        raise ValueError("Couldn't find any segments in this script")
    return ParsedScript(title=str(data.get("title") or "Untitled script").strip(), segments=segments)
