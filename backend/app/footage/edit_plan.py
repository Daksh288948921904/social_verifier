import json
import logging
import re

from app.core import db
from app.core.config import settings
from app.core.groq_pool import call_rotating

logger = logging.getLogger(__name__)

WORDS_PER_SECOND = 2.5  # ~150 wpm, a typical news-read pace
MAX_CANDIDATES = 12
SHORT_CLIP_TOLERANCE = 3.0  # seconds a clip may run short of its narration before it's flagged

SYSTEM_PROMPT = """You are a news video editor building the edit plan for one segment of a
broadcast. You get the segment's script with numbered lines, and a numbered list of footage
moments already found for it (each with what it shows, what script it fits, and a 0-100 score).

Split the script, in order, into consecutive beats. Each beat is either:
- "anchor": the presenter on camera. Use for show/segment openings and sign-offs ("I'm ...",
  "This is ..."), the host's own opinion, argument and conclusions, direct address to the viewer
  ("you", "let me"), lists of principles or calls to action, and any line no moment genuinely shows.
- "clip": a footage moment plays while the anchor's narration continues as voice-over. Use only
  when the narration describes events, people, places, quotes or data that the moment actually
  shows.

Rules:
- Beats must cover every line, in order, with no gaps or overlaps. Give each beat's first line.
- Prefer moments with score 50+; never use one below 40. Don't force footage where none fits.
- Use each moment at most once. Keep beats meaningful (usually 2-12 lines); don't flip between
  anchor and clip every line.
- "note": one short line of direction for the editor (e.g. "cold open on anchor, slow push-in",
  "VO over defendants entering the dock", "hold on Jackson's face for the quote").

Respond with JSON only:
{"beats": [{"start_line": 1, "type": "anchor" | "clip", "moment": <moment number, clip only>,
            "note": "..."}]}
"""


def _segment_candidates(segment_id: str) -> list[dict]:
    """Every moment found for this segment, across all its keywords, best
    first -- deduplicated, since the same moment can come back under two
    keywords."""
    rows = db.fetch_all(
        "SELECT v.*, k.id AS keyword_id, k.text AS keyword_text FROM footage_videos v "
        "JOIN footage_keywords k ON k.id = v.keyword_id WHERE k.segment_id=? AND v.relevance >= 0",
        (segment_id,),
    )
    seen: set[tuple] = set()
    candidates = []
    for v in rows:
        for m in json.loads(v["moments_json"] or "[]"):
            key = (v["video_id"], m["start"], m["end"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "video_row_id": v["id"],
                "keyword_id": v["keyword_id"],
                "keyword_text": v["keyword_text"],
                "video_id": v["video_id"],
                "video_title": v["title"],
                "channel": v["channel"],
                "thumbnail_url": v["thumbnail_url"],
                "start": m["start"],
                "end": m["end"],
                "label": m.get("label", ""),
                "description": m.get("description", ""),
                "fit": m.get("fit", ""),
                "score": m.get("score", 0),
                "estimated": bool(m.get("estimated")),
            })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:MAX_CANDIDATES]


def _seconds(text: str) -> float:
    return round(len(text.split()) / WORDS_PER_SECOND, 1)


def _beat(kind: str, lines: list[str], note: str, clip: dict | None = None) -> dict:
    text = "\n".join(lines)
    beat = {"type": kind, "text": text, "est_seconds": _seconds(text), "note": note, "clip": clip}
    if clip:
        clip_len = clip["end"] - clip["start"]
        beat["clip_short_by"] = round(max(0.0, beat["est_seconds"] - clip_len), 1) \
            if beat["est_seconds"] - clip_len > SHORT_CLIP_TOLERANCE else 0.0
    return beat


def _plan_segment(segment: dict) -> list[dict]:
    lines = [l for l in segment["script_excerpt"].splitlines() if l.strip()]
    if not lines:
        return []
    candidates = _segment_candidates(segment["id"])
    if not candidates:
        return [_beat("anchor", lines, "No footage fetched for this segment yet -- anchor on camera.")]

    numbered = "\n".join(f"{i + 1}: {l}" for i, l in enumerate(lines))
    moments = "\n".join(
        f"M{i + 1} (score {c['score']}, {c['end'] - c['start']:.0f}s): \"{c['label']}\" from "
        f"\"{c['video_title']}\" -- shows: {c['description']} -- fits: {c['fit']}"
        for i, c in enumerate(candidates)
    )
    response = call_rotating(lambda client: client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"SEGMENT: {segment['title']}\nSummary: {segment['summary']}\n\n"
                f"SCRIPT LINES:\n{numbered}\n\nFOOTAGE MOMENTS:\n{moments}"
            )},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        reasoning_effort="low",
    ))
    raw = [b for b in json.loads(response.choices[0].message.content).get("beats") or [] if isinstance(b, dict)]

    # Same guard as script_parse: only the start lines come from the LLM, so
    # clamp/order them and slice the text back out of the real script --
    # every line ends up in exactly one beat no matter what came back.
    starts = []
    for b in raw:
        try:
            starts.append(max(1, min(len(lines), int(b.get("start_line", 1)))))
        except (TypeError, ValueError):
            starts.append(1)
    if starts:
        starts[0] = 1
    for i in range(1, len(starts)):
        starts[i] = max(starts[i], starts[i - 1])

    beats: list[dict] = []
    used: set[int] = set()
    for i, b in enumerate(raw):
        end = starts[i + 1] - 1 if i + 1 < len(starts) else len(lines)
        chunk = lines[starts[i] - 1:end]
        if not chunk:
            continue
        clip = None
        if b.get("type") == "clip":
            # Moments are listed as "M3" in the prompt, so the answer comes
            # back as 3, "3" or "M3" -- take the number either way.
            digits = re.search(r"\d+", str(b.get("moment") or ""))
            idx = int(digits.group()) - 1 if digits else -1
            if 0 <= idx < len(candidates) and idx not in used and candidates[idx]["score"] >= 40:
                used.add(idx)
                clip = candidates[idx]
        note = str(b.get("note") or "").strip()
        kind = "clip" if clip else "anchor"
        # Merge back-to-back anchor beats -- two anchor rows in a row read as
        # one continuous piece to camera anyway.
        if kind == "anchor" and beats and beats[-1]["type"] == "anchor":
            prev = beats.pop()
            chunk = prev["text"].split("\n") + chunk
            note = prev["note"] or note
        beats.append(_beat(kind, chunk, note, clip))

    if not beats:  # the LLM returned nothing usable -- fall back to all-anchor
        beats = [_beat("anchor", lines, "")]
    return beats


def build_edit_plan(project_id: str) -> dict:
    segments = db.fetch_all(
        "SELECT id, position, title, summary, script_excerpt FROM footage_segments "
        "WHERE project_id=? ORDER BY position",
        (project_id,),
    )
    plan_segments = []
    for s in segments:
        s = dict(s)
        beats = _plan_segment(s)
        plan_segments.append({
            "segment_id": s["id"], "position": s["position"], "title": s["title"], "beats": beats,
        })
    return {"segments": plan_segments}


def count_moments(project_id: str) -> int:
    """Total moments currently found -- stored with a plan so the UI can tell
    when newer results have arrived since it was built."""
    rows = db.fetch_all(
        "SELECT v.moments_json FROM footage_videos v JOIN footage_keywords k ON k.id = v.keyword_id "
        "WHERE k.project_id=? AND v.relevance >= 0",
        (project_id,),
    )
    return sum(len(json.loads(r["moments_json"] or "[]")) for r in rows)
