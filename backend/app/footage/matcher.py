import json
import logging
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.groq_pool import call_rotating
from app.footage.transcript import VideoTranscript

logger = logging.getLogger(__name__)

TRANSCRIPT_BUDGET_CHARS = 8_000
MAX_MOMENTS = 4

_STOPWORDS = set("""
the and for that with this from have has had was were are not but they their them what when
where which who will would could should about into than then there these those been being its
it's our your you his her she him over under after before also only just more most very such
said says like all any can one two out who why how did does doing done
""".split())
_WORD_RE = re.compile(r"[a-z0-9À-ɏ]{3,}")

SYSTEM_PROMPT = """You help a video editor find usable footage. You get one segment of a broadcast
script, the YouTube search query that was run for it, and one candidate video: its metadata,
chapters, and a timestamped transcript (possibly with gaps marked "…" where less relevant parts
were left out).

Find the specific moments in this video that could be cut and used on screen for this segment:
a speech or quote the script mentions, archival footage of the event, a report that explains the
same facts, interviews with the people named, and so on.

Rules:
- Timestamps must come from the transcript lines (or chapter starts). Never invent times beyond
  the video's duration.
- Each moment should be 10-120 seconds long.
- At most 4 moments, best first. Return no moments if nothing in the video genuinely fits.
- Without a transcript, judge only from the title, description and chapters. Return at most one
  moment (or one per relevant chapter), and keep it to what the title/description clearly implies.
- This is for news/documentary use: if the video is a movie, TV drama, reenactment, AI-generated
  or colourised/"brought to life" edit rather than real footage, say so plainly at the start of the
  verdict and cap relevance at 40 unless the segment explicitly calls for that kind of material.

Respond with JSON only:
{"relevance": <0-100, how useful this video is overall for the segment>,
 "verdict": "<1-2 sentences: what this video is, and how (or whether) it serves the segment>",
 "moments": [{"start": <seconds>, "end": <seconds>,
              "label": "<3-8 word title of the moment>",
              "description": "<what is shown or said in this part, concretely>",
              "fit": "<which part or line of the script this covers, and why>",
              "score": <0-100>}]}
"""


@dataclass
class VideoMatch:
    relevance: int = 0
    verdict: str = ""
    moments: list[dict] = field(default_factory=list)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _fmt_ts(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def condense_transcript(lines: list[dict], focus: dict[str, int]) -> str:
    """The whole transcript when it fits the budget; otherwise the lines that
    share the most words with the segment/keyword (plus one line either side
    for context), kept in time order with "…" marking what was left out.
    Long documentaries run 15k+ tokens of captions, almost all of it
    irrelevant to any one segment -- this keeps every LLM call small enough
    for the shared Groq rate limits without losing the parts that matter."""
    rendered = [f"[{_fmt_ts(l['start'])}] {l['text']}" for l in lines]
    if sum(len(r) + 1 for r in rendered) <= TRANSCRIPT_BUDGET_CHARS:
        return "\n".join(rendered)

    scores = [sum(focus.get(w, 0) for w in _tokens(l["text"])) for l in lines]
    ranked = sorted(range(len(lines)), key=lambda i: scores[i], reverse=True)
    chosen: set[int] = set()
    used = 0
    for i in ranked:
        if scores[i] == 0:
            break
        for j in (i - 1, i, i + 1):
            if 0 <= j < len(lines) and j not in chosen:
                if used + len(rendered[j]) + 1 > TRANSCRIPT_BUDGET_CHARS:
                    continue
                chosen.add(j)
                used += len(rendered[j]) + 1
        if used >= TRANSCRIPT_BUDGET_CHARS * 0.95:
            break
    if not chosen:  # nothing overlaps at all -- fall back to the opening
        chosen = set(range(min(len(lines), 25)))

    out: list[str] = []
    prev = -1
    for i in sorted(chosen):
        if prev != -1 and i != prev + 1:
            out.append("…")
        out.append(rendered[i])
        prev = i
    return "\n".join(out)


def _focus_weights(segment: dict, keyword: dict) -> dict[str, int]:
    weights: dict[str, int] = {}
    for text, weight in (
        (segment.get("script_excerpt", ""), 1),
        (segment.get("summary", ""), 1),
        (segment.get("title", ""), 2),
        (segment.get("visual_needs", ""), 2),
        (keyword["text"], 3),
    ):
        for w in _tokens(text):
            weights[w] = max(weights.get(w, 0), weight)
    return weights


def match_video(segment: dict, keyword: dict, video: dict, transcript: VideoTranscript) -> VideoMatch:
    duration = transcript.duration_seconds
    parts = [
        f"SCRIPT SEGMENT: {segment['title']}",
        f"Summary: {segment.get('summary') or '(none)'}",
        f"Footage wanted: {segment.get('visual_needs') or '(not specified)'}",
    ]
    if segment.get("script_excerpt"):
        parts.append(f"Script text:\n{segment['script_excerpt'][:2500]}")
    parts += [
        "",
        f"SEARCH QUERY: {keyword['text']}" + (f" -- {keyword['rationale']}" if keyword.get("rationale") else ""),
        "",
        f"VIDEO: {video['title']}",
        f"Channel: {transcript.channel or video.get('channel') or 'unknown'}",
        f"Duration: {_fmt_ts(duration) if duration else 'unknown'}",
        f"Description: {(video.get('description') or '')[:600]}",
    ]
    if transcript.chapters:
        parts.append("Chapters:\n" + "\n".join(
            f"[{_fmt_ts(c['start'])}] {c['title']}" for c in transcript.chapters[:40]
        ))
    if transcript.lines:
        parts.append("Transcript:\n" + condense_transcript(transcript.lines, _focus_weights(segment, keyword)))
    else:
        parts.append("Transcript: (not available for this video)")

    response = call_rotating(lambda client: client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(parts)},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        reasoning_effort="low",
    ))
    try:
        data = json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Malformed match response for video %s", video.get("video_id"))
        return VideoMatch(verdict="Couldn't analyse this video.")
    match = _clean(data, duration)
    if not transcript.lines:
        # Times picked without captions are the model's guess from the title,
        # description or chapters -- flag them so the UI can say so.
        for m in match.moments:
            m["estimated"] = True
    return match


def _clamp_int(value, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(float(value))))
    except (TypeError, ValueError):
        return lo


def _clean(data: dict, duration: float | None) -> VideoMatch:
    moments = []
    for m in data.get("moments") or []:
        if not isinstance(m, dict):
            continue
        try:
            start = max(0.0, float(m.get("start", 0)))
            end = float(m.get("end", start + 30))
        except (TypeError, ValueError):
            continue
        if duration:
            if start >= duration:
                continue
            end = min(end, duration)
        if end <= start:
            end = start + 30 if not duration else min(start + 30, duration)
        moments.append({
            "start": round(start, 1),
            "end": round(end, 1),
            "label": str(m.get("label") or "").strip(),
            "description": str(m.get("description") or "").strip(),
            "fit": str(m.get("fit") or "").strip(),
            "score": _clamp_int(m.get("score"), 0, 100),
        })
    moments.sort(key=lambda m: m["score"], reverse=True)
    return VideoMatch(
        relevance=_clamp_int(data.get("relevance"), 0, 100),
        verdict=str(data.get("verdict") or "").strip(),
        moments=moments[:MAX_MOMENTS],
    )
