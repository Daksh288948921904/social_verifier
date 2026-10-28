import json
import logging
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.groq_pool import call_rotating

logger = logging.getLogger(__name__)

MAX_SCRIPT_CHARS = 60_000
# Groq's free tier allows 8k tokens per request-minute, prompt and answer
# together: ~1k for the system prompt, ~3.5k (≈12k chars) of script, and
# up to 3k for the JSON answer.
CHUNK_CHARS = 12_000
MAX_ANSWER_TOKENS = 3_000

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


def _has_text(line: str) -> bool:
    return any(c.isalnum() for c in line)


def _chunks(lines: list[str]) -> list[tuple[int, int]]:
    """Splits the script into 1-based, inclusive line ranges whose numbered
    text fits CHUNK_CHARS. Groq's on-demand tier caps a single request at
    8k tokens per minute (prompt + answer), so a long script sent in one go
    is rejected outright (413) no matter which key it goes to. Each part
    ends at a segment marker or blank line where one is near, so the forced
    break lands on a natural boundary."""
    def cost(j: int) -> int:
        return len(f"{j}: {lines[j - 1]}\n") if _has_text(lines[j - 1]) else 0

    chunks: list[tuple[int, int]] = []
    start, size = 1, 0
    # Last line before a marker / last blank line / last line ending a sentence.
    marker_end = blank_end = sentence_end = 0
    for i in range(1, len(lines) + 1):
        line = lines[i - 1].strip()
        if i > start and _MARKER_RE.match(line):
            marker_end = i - 1
        elif i > start and not line:
            blank_end = i
        elif i > start and line.endswith((".", "!", "?", '."', ".”", "?”", "!”")):
            sentence_end = i
        size += cost(i)
        if size > CHUNK_CHARS and i > start:
            span = i - start
            if marker_end - start >= span // 2:  # a marker in the back half
                end = marker_end
            elif blank_end - start >= span * 2 // 3:  # a blank line in the last third
                end = blank_end
            elif sentence_end - start >= span * 2 // 3:  # a full stop in the last third
                end = sentence_end
            else:
                end = i - 1
            chunks.append((start, end))
            start, marker_end, blank_end, sentence_end = end + 1, 0, 0, 0
            size = sum(cost(j) for j in range(start, i + 1))
    chunks.append((start, len(lines)))
    return [c for c in chunks if c[0] <= c[1]]


def _parse_chunk(lines: list[str], first: int, last: int, used_queries: list[str], part: str) -> dict:
    # Drop pure separator lines (e.g. "· · ·") from the numbered view so they
    # don't waste tokens; their line numbers stay valid for slicing.
    numbered = "\n".join(
        f"{i}: {lines[i - 1]}" for i in range(first, last + 1) if _has_text(lines[i - 1])
    )
    note = ""
    if part:
        note = f"This is {part} of a longer script; the first segment here starts at line {first}.\n"
        if used_queries:
            note += "Queries already used for earlier parts (don't repeat): " + "; ".join(used_queries[-30:]) + "\n"
        note += "\n"
    response = call_rotating(lambda client: client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": note + numbered},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        reasoning_effort="low",
        max_completion_tokens=MAX_ANSWER_TOKENS,
    ))
    return json.loads(response.choices[0].message.content)


def parse_script(script: str) -> ParsedScript:
    """Splits a script into segments with suggested search keywords. The LLM
    only returns each segment's *first line number*, never the text itself --
    the excerpts are sliced back out of the original script here, so a long
    script costs no extra output tokens and its wording can't be paraphrased
    or truncated along the way. Long scripts go in several parts (see
    _chunks); line numbers are global, so the parts stitch back together."""
    lines = [line.rstrip() for line in script[:MAX_SCRIPT_CHARS].splitlines()]
    chunks = _chunks(lines)

    title = ""
    raw_segments: list[dict] = []
    starts: list[int] = []
    used_queries: list[str] = []
    for n, (first, last) in enumerate(chunks):
        part = f"part {n + 1} of {len(chunks)}" if len(chunks) > 1 else ""
        data = _parse_chunk(lines, first, last, used_queries, part)
        title = title or str(data.get("title") or "")
        chunk_segments = [s for s in data.get("segments") or [] if isinstance(s, dict)]
        for j, s in enumerate(chunk_segments):
            try:
                start = max(first, min(last, int(s.get("start_line", first))))
            except (TypeError, ValueError):
                start = first
            # Each part's first segment begins where the part does, so no
            # lines fall between parts.
            starts.append(first if j == 0 else start)
            raw_segments.append(s)
            used_queries += [str(k.get("text", "")).strip() for k in s.get("keywords") or [] if isinstance(k, dict)]

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
    return ParsedScript(title=title.strip() or "Untitled script", segments=segments)
