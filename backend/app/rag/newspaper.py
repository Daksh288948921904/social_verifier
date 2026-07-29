import json
import logging

from app.core import db
from app.core.config import settings
from app.core.groq_pool import next_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the editor of a daily newspaper laying out today's front page from
live TV news coverage. You are given every clip captured during one monitoring session, each
with an id, a title, a summary, and its timestamp in the broadcast.

Write the paper's content as a single JSON object matching this schema exactly:
{
  "masthead": string,          // a short, generic newspaper name for this publication, e.g.
                                // "THE DAILY DISPATCH" -- invent something newspaper-sounding;
                                // do not reference "AI", "live stream", or any software.
  "sections": [
    {
      "name": string,          // e.g. "Politics", "World", "Sports" -- only sections that
                                // actually have stories; do not force empty ones
      "articles": [
        {
          "clip_id": string,   // must be one of the given clip ids, verbatim
          "headline": string,  // punchy newspaper headline, distinct from the clip's own title
          "body": string       // 2-5 sentence article body in newspaper prose, drawn only
                                // from the given summary -- do not invent facts
        }
      ]
    }
  ]
}

Order sections by apparent prominence/airtime in the broadcast. Within each section, order
articles the same way. The very first article of the very first section is the lead,
front-page story, so give it your strongest headline.

Respond with only that JSON object, no other text.
"""

FALLBACK_MASTHEAD = "THE DAILY DISPATCH"


def _clean(data: dict, valid_ids: set[str]) -> dict:
    """Drops any hallucinated clip_id or malformed article rather than
    letting one bad entry break the whole front page."""
    sections = []
    for section in data.get("sections") or []:
        articles = [
            {"clip_id": a["clip_id"], "headline": a["headline"], "body": a["body"]}
            for a in (section.get("articles") or [])
            if a.get("clip_id") in valid_ids and a.get("headline") and a.get("body")
        ]
        if articles:
            sections.append({"name": section.get("name") or "", "articles": articles})
    return {"masthead": data.get("masthead") or FALLBACK_MASTHEAD, "sections": sections}


def generate_newspaper(session_id: str) -> str:
    rows = db.fetch_all(
        "SELECT id, title, summary FROM clips WHERE session_id=? AND status!='deleted' "
        "ORDER BY start_seconds",
        (session_id,),
    )
    if not rows:
        result = {"masthead": FALLBACK_MASTHEAD, "sections": []}
    else:
        valid_ids = {r["id"] for r in rows}
        stories = "\n\n".join(
            f"- id: {r['id']}\n  Title: {r['title']}\n  Summary: {r['summary']}" for r in rows
        )
        client = next_client()
        response = client.chat.completions.create(
            model=settings.segmentation_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Today's captured stories:\n\n{stories}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        try:
            result = _clean(json.loads(response.choices[0].message.content), valid_ids)
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.exception("Malformed newspaper response; falling back to an empty front page")
            result = {"masthead": FALLBACK_MASTHEAD, "sections": []}

    content = json.dumps(result)
    db.execute(
        "INSERT INTO session_newspapers (session_id, content, created_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(session_id) DO UPDATE SET content=excluded.content, created_at=excluded.created_at",
        (session_id, content),
    )
    return content


FULL_ARTICLE_SYSTEM_PROMPT = """You are a newspaper reporter writing the full, detailed version
of a story that ran as a short front-page teaser. You are given the story's headline, its short
teaser summary, and the actual broadcast transcript excerpt it was based on.

Write a complete newspaper article (roughly 4-8 paragraphs) in professional news-reporting prose,
grounded only in what the transcript excerpt actually says -- do not invent quotes, names,
numbers, or facts that aren't present in it. If the transcript excerpt is thin, write a shorter
article rather than padding it with invented detail.

Respond with only the article body text -- no headline, no JSON, no markdown formatting.
"""


def generate_full_article(clip_id: str) -> str:
    """Expands one clip's short teaser into a full article, grounded in the
    actual transcript for that clip's time range rather than just
    rephrasing the existing short summary into a longer-sounding but
    content-thin paragraph. Cached in clip_articles since the source
    transcript never changes once a clip is cut."""
    cached = db.fetch_one("SELECT article FROM clip_articles WHERE clip_id=?", (clip_id,))
    if cached:
        return cached["article"]

    clip = db.fetch_one(
        "SELECT session_id, title, summary, start_seconds, end_seconds FROM clips WHERE id=?",
        (clip_id,),
    )
    if not clip:
        raise ValueError(f"clip {clip_id} not found")

    segments = db.fetch_all(
        "SELECT text FROM transcript_segments WHERE session_id=? "
        "AND absolute_start < ? AND absolute_end > ? ORDER BY absolute_start",
        (clip["session_id"], clip["end_seconds"], clip["start_seconds"]),
    )
    transcript = "\n".join(s["text"] for s in segments) or clip["summary"]

    client = next_client()
    response = client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": FULL_ARTICLE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Headline: {clip['title']}\nTeaser: {clip['summary']}\n\n"
                    f"Transcript excerpt:\n{transcript}"
                ),
            },
        ],
        temperature=0.4,
    )
    article = response.choices[0].message.content

    db.execute(
        "INSERT INTO clip_articles (clip_id, article, created_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(clip_id) DO UPDATE SET article=excluded.article, created_at=excluded.created_at",
        (clip_id, article),
    )
    return article
