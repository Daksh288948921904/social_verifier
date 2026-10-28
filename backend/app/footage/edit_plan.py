import hashlib
import json
import logging
import re

from app.core import db
from app.core.groq_pool import call_models

logger = logging.getLogger(__name__)

WORDS_PER_SECOND = 2.5  # ~150 wpm, a typical news-read pace
SHORT_CLIP_TOLERANCE = 3.0  # seconds a clip may run short of its narration before it's flagged
MAX_ADDED_CHARS = 2000  # cap on anchor wording typed into the plan by hand

MAX_AI_CANDIDATES = 12
MIN_AI_SCORE = 40
PLAN_MODES = ("picks", "auto", "mixed")

SYSTEM_PROMPT = """You are a news video editor building the edit plan for one segment of a
broadcast. You get the segment's script with numbered lines, and a numbered list of footage clips.
Each clip is tagged either [EDITOR'S PICK] (chosen by hand) or [AI SUGGESTION, score N] (found
automatically, scored 0-100 for how well it fits).

Split the script, in order, into consecutive beats. Each beat is either:
- "anchor": the presenter on camera. Use for show/segment openings and sign-offs ("I'm ...",
  "This is ..."), the host's own opinion, argument and conclusions, direct address to the viewer
  ("you", "let me"), lists of principles or calls to action, and any line no clip genuinely shows.
- "clip": a clip plays while the anchor's narration continues as voice-over, over the lines whose
  content that clip shows.

Rules:
- Beats must cover every line, in order, with no gaps or overlaps. Give each beat's first line.
- [EDITOR'S PICK] clips were chosen on purpose: place every one on the lines it fits best, and
  leave one out only if it genuinely matches nothing in this segment.
- [AI SUGGESTION] clips are optional: use one only where the narration describes events, people,
  places, quotes or data that it actually shows. Prefer score 50+; never below 40. Don't force them.
- Use each clip at most once. Keep beats meaningful (usually 2-12 lines); don't flip between
  anchor and clip every line.
- "note": one short line of direction for the editor (e.g. "cold open on anchor, slow push-in",
  "VO over defendants entering the dock", "hold on Jackson's face for the quote").

Respond with JSON only:
{"beats": [{"start_line": 1, "type": "anchor" | "clip", "moment": <clip number, clip only>,
            "note": "..."}]}
"""


def _picked_clips(segment_id: str) -> list[dict]:
    """The clips the editor pushed to the plan for this segment, in the order
    they were pushed."""
    rows = db.fetch_all(
        "SELECT p.*, k.text AS keyword_text FROM footage_picks p "
        "LEFT JOIN footage_keywords k ON k.id = p.keyword_id "
        "WHERE p.segment_id=? ORDER BY p.created_at, p.start_seconds",
        (segment_id,),
    )
    return [
        {
            "pick_id": r["id"],
            "keyword_id": r["keyword_id"],
            "keyword_text": r["keyword_text"] or "",
            "video_id": r["video_id"],
            "video_title": r["video_title"],
            "channel": r["channel"],
            "thumbnail_url": r["thumbnail_url"],
            "start": r["start_seconds"],
            "end": r["end_seconds"],
            "label": r["label"],
            "description": r["description"],
            "source": r["source"],  # 'suggested' | 'custom'
            "score": None,
            "clip_audio": bool(r["clip_audio"]),  # the editor's sound choice when pushing
        }
        for r in rows
    ]


def _ai_clips(segment_id: str) -> list[dict]:
    """The best moments the AI found for this segment across all its
    keywords -- deduplicated (the same moment can come back under two
    keywords), best first, and only those scoring at least MIN_AI_SCORE."""
    rows = db.fetch_all(
        "SELECT v.*, k.id AS keyword_id, k.text AS keyword_text FROM footage_videos v "
        "JOIN footage_keywords k ON k.id = v.keyword_id WHERE k.segment_id=? AND v.relevance >= 0",
        (segment_id,),
    )
    seen: set[tuple] = set()
    clips = []
    for v in rows:
        for m in json.loads(v["moments_json"] or "[]"):
            key = (v["video_id"], m["start"], m["end"])
            if key in seen or m.get("score", 0) < MIN_AI_SCORE:
                continue
            seen.add(key)
            clips.append({
                "pick_id": None,
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
                "source": "ai",
                "score": m.get("score", 0),
            })
    clips.sort(key=lambda c: c["score"], reverse=True)
    return clips[:MAX_AI_CANDIDATES]


def _segment_candidates(segment_id: str, mode: str) -> list[dict]:
    """Which clips the plan may use, by mode:
    - "picks": only what the editor pushed;
    - "auto": only the AI's best moments (picks are ignored);
    - "mixed": the editor's picks (always placed) plus the AI's best moments
      to fill the gaps -- minus any the editor already picked."""
    picks = _picked_clips(segment_id) if mode in ("picks", "mixed") else []
    if mode == "picks":
        return picks
    taken = {(p["video_id"], p["start"], p["end"]) for p in picks}
    ai = [c for c in _ai_clips(segment_id) if (c["video_id"], c["start"], c["end"]) not in taken]
    return picks + ai


def _seconds(text: str) -> float:
    return round(len(text.split()) / WORDS_PER_SECOND, 1)


def _beat(
    kind: str, lines: list[str], note: str, clip: dict | None = None,
    added: bool = False, clip_audio: bool = False,
) -> dict:
    """added: the beat isn't part of the script -- extra anchor wording, or a
    clip dropped in between beats that plays on its own. clip_audio: keep the
    scraped clip's original sound (otherwise it runs muted under the VO)."""
    text = "\n".join(lines).strip("\n")
    beat = {"type": kind, "text": text, "est_seconds": _seconds(text), "note": note, "clip": clip,
            "added": added, "clip_audio": bool(clip) and clip_audio}
    if clip:
        clip_len = clip["end"] - clip["start"]
        if not text:  # nothing read over it: the beat lasts as long as the clip
            beat["est_seconds"] = round(clip_len, 1)
        beat["clip_short_by"] = round(max(0.0, beat["est_seconds"] - clip_len), 1) \
            if beat["est_seconds"] - clip_len > SHORT_CLIP_TOLERANCE else 0.0
    return beat


def _plan_segment(segment: dict, mode: str) -> list[dict]:
    lines = [l for l in segment["script_excerpt"].splitlines() if l.strip()]
    if not lines:
        return []
    candidates = _segment_candidates(segment["id"], mode)
    if not candidates:
        reason = {
            "picks": "No clips pushed to the plan for this segment",
            "auto": "No footage found for this segment yet",
            "mixed": "No clips pushed or found for this segment",
        }[mode]
        return [_beat("anchor", lines, f"{reason} -- anchor on camera.")]

    numbered = "\n".join(f"{i + 1}: {l}" for i, l in enumerate(lines))
    moments = "\n".join(
        f"C{i + 1} "
        + ("[EDITOR'S PICK]" if c["source"] != "ai" else f"[AI SUGGESTION, score {c['score']}]")
        + f" ({c['end'] - c['start']:.0f}s): \"{c['label'] or 'untitled clip'}\" from \"{c['video_title']}\""
        + (f" -- shows: {c['description']}" if c["description"] else "")
        for i, c in enumerate(candidates)
    )
    response = call_models(lambda client, model: client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"SEGMENT: {segment['title']}\nSummary: {segment['summary']}\n\n"
                f"SCRIPT LINES:\n{numbered}\n\nPICKED CLIPS:\n{moments}"
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
            # Clips are listed as "C3" in the prompt, so the answer comes
            # back as 3, "3" or "C3" -- take the number either way.
            digits = re.search(r"\d+", str(b.get("moment") or ""))
            idx = int(digits.group()) - 1 if digits else -1
            if 0 <= idx < len(candidates) and idx not in used:
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
        beats.append(_beat(kind, chunk, note, clip, clip_audio=bool(clip and clip.get("clip_audio"))))

    if not beats:  # the LLM returned nothing usable -- fall back to all-anchor
        beats = [_beat("anchor", lines, "")]
    return beats


def build_edit_plan(project_id: str, mode: str) -> dict:
    segments = db.fetch_all(
        "SELECT id, position, title, summary, script_excerpt FROM footage_segments "
        "WHERE project_id=? ORDER BY position",
        (project_id,),
    )
    plan_segments = []
    for s in segments:
        s = dict(s)
        beats = _plan_segment(s, mode)
        plan_segments.append({
            "segment_id": s["id"], "position": s["position"], "title": s["title"], "beats": beats,
        })
    return {"mode": mode, "segments": plan_segments}


def plan_signature(project_id: str, mode: str) -> str:
    """Fingerprint of everything a plan in this mode was built from -- the
    pushed clips (picks/mixed) and/or the AI moments found (auto/mixed) --
    so the UI can tell when the plan is out of date."""
    parts = [mode]
    if mode in ("picks", "mixed"):
        rows = db.fetch_all("SELECT id FROM footage_picks WHERE project_id=? ORDER BY id", (project_id,))
        parts.append(",".join(r["id"] for r in rows))
    if mode in ("auto", "mixed"):
        rows = db.fetch_all(
            "SELECT v.id, v.moments_json FROM footage_videos v JOIN footage_keywords k ON k.id = v.keyword_id "
            "WHERE k.project_id=? AND v.relevance >= 0 ORDER BY v.id",
            (project_id,),
        )
        parts.append(",".join(f"{r['id']}:{len(json.loads(r['moments_json'] or '[]'))}" for r in rows))
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


CLIP_FIELDS = (
    "pick_id", "keyword_id", "keyword_text", "video_id", "video_title", "channel", "thumbnail_url",
    "start", "end", "label", "description", "source", "score", "clip_audio",
)


class PlanEditError(ValueError):
    pass


def _clean_clip(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    clip = {k: raw.get(k) for k in CLIP_FIELDS}
    try:
        clip["start"], clip["end"] = float(clip["start"]), float(clip["end"])
    except (TypeError, ValueError):
        raise PlanEditError("A clip is missing its start/end time")
    if not clip["video_id"] or clip["end"] <= clip["start"]:
        raise PlanEditError("A clip has an invalid video or time range")
    if clip["source"] not in ("suggested", "custom", "ai"):
        clip["source"] = "custom"
    for k in ("keyword_text", "video_title", "channel", "label", "description"):
        clip[k] = str(clip[k] or "")
    return clip


def apply_plan_edit(current: dict, edited_segments: list) -> dict:
    """Takes the editor's hand-edited beats for one or more segments and
    rebuilds them through _beat(), so durations and short-clip warnings are
    always recomputed server-side and back-to-back anchor beats merge. The
    script itself is never editable here: each segment's lines must come
    back exactly as they were, only regrouped -- otherwise the edit is
    rejected rather than silently losing or changing a line. Beats marked
    "added" (the anchor's own extra wording, or a clip inserted between
    beats) sit outside the script and are free to add, edit or delete."""
    by_id = {s["segment_id"]: s for s in current.get("segments", [])}
    for edited in edited_segments:
        seg = by_id.get(edited.get("segment_id")) if isinstance(edited, dict) else None
        if seg is None:
            raise PlanEditError("Edited segment isn't part of this plan")
        original_lines = [l for b in seg["beats"] if not b.get("added") for l in b["text"].split("\n")]
        beats: list[dict] = []
        new_lines: list[str] = []
        for raw in edited.get("beats") or []:
            if not isinstance(raw, dict):
                continue
            added = bool(raw.get("added"))
            text = str(raw.get("text") or "")
            clip = _clean_clip(raw.get("clip")) if raw.get("type") == "clip" else None
            clip_audio = bool(raw.get("clip_audio"))
            note = str(raw.get("note") or "").strip()
            if added:
                text = text.strip()
                if len(text) > MAX_ADDED_CHARS:
                    raise PlanEditError(f"Added anchor wording is limited to {MAX_ADDED_CHARS} characters")
                if not clip and not text:
                    continue  # an empty added anchor line is just dropped
                beats.append(_beat("clip" if clip else "anchor", text.split("\n") if text else [],
                                   note, clip, added=True, clip_audio=clip_audio))
                continue
            lines = text.split("\n")
            if not any(l.strip() for l in lines):
                continue
            new_lines += lines
            # Merge back-to-back script anchor beats; added ones stay their own row.
            if clip is None and beats and beats[-1]["type"] == "anchor" and not beats[-1]["added"]:
                prev = beats.pop()
                lines = prev["text"].split("\n") + lines
                note = prev["note"] or note
            beats.append(_beat("clip" if clip else "anchor", lines, note, clip, clip_audio=clip_audio))
        if new_lines != original_lines:
            raise PlanEditError(f"Script lines in \"{seg['title']}\" don't match the original")
        seg["beats"] = beats
    current["edited"] = True
    return current
