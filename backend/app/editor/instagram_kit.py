import base64
import json
from pathlib import Path

from app.core import db
from app.core.config import settings
from app.core.groq_pool import call_with_retry, next_client
from app.core.openai_client import get_client as get_openai_client

CURATED_AUDIO_OPTIONS = """Named audio picks by content mood -- REAL, well-known tracks that have
been long-standing Instagram Reels favorites in India for each mood (NOT live trending-chart
data; these are evergreen go-tos, not guaranteed to be this week's specific trend):

- Serious/alarming claim (verdict false or misleading, high-stakes topic): the suspense classical
  staple "In the Hall of the Mountain King" (Grieg) for a tense building edit, or the moody
  "Drishyam" (2015) background score for an investigative-thriller feel.
- Claim busted / myth debunked (satisfying reveal): a comedic "record scratch and freeze" sting,
  or the "Metro Boomin' Heart Attack" whoosh-drop meme sound widely reused for reveal-twist edits.
- Claim confirmed true / serious but validated: a steady, minimal news-drum-and-brass sting like
  those used in Indian prime-time news package intros.
- Tragic or sensitive real-world topic: "Kesariya" (Brahmastra, 2022) instrumental/piano cut, or
  any slow solo piano rendition -- widely used for somber emotional Reels edits in India.
- High-energy political or viral topic: "Kaavaalaa" (Jailer, 2023) or "Zinda Banda" (Jawan, 2023)
  -- both huge, still widely reused pan-India dance/hype tracks for fast-cut Reels.
- Dialogue-driven claims (a public figure's exact words being fact-checked): a dramatic Bollywood
  dialogue-drop audio (e.g. a famous confrontation-scene dialogue clip) fits thematically since
  the content centers on someone's own words being scrutinized.
"""

KIT_PROMPT = f"""You are a social-media strategist preparing a completed fact-check video for
posting as an Instagram Reel. You are given the video's headline claims and overall conclusion.

Produce three things:
1. "caption": An engaging Instagram caption (2-4 short lines/paragraphs) written to maximize
   watch-through and shares for a fact-check/news-debunking Reel. End with 5-8 relevant hashtags.
2. "best_time": A specific day-part and rough time range recommendation for when to post THIS
   type of content (e.g. a news/political fact-check) based on well-established general social
   media engagement patterns (commute hours, lunch, evening, weekday vs weekend). Explicitly
   note that this is a general heuristic, not analytics from the poster's actual account, which
   you have no access to.
3. "audio_style": Pick the single best-fitting option for this content's mood/verdict from the
   curated list below and NAME THE ACTUAL TRACK by its title (and artist/film if given), not just
   a genre description -- e.g. "Kesariya (Brahmastra)" not just "emotional piano". Briefly say
   why it fits this specific claim/verdict. Label it as "a long-standing Reels favorite in India
   for this mood" -- NOT as currently trending this week, since you have no access to Instagram's
   live trending-audio charts. End by telling the user this exact track (or one with a similar
   feel) should be searchable in Instagram's own audio picker, and to swap it for whatever is
   trending that specific week if they want maximum algorithmic reach.

{CURATED_AUDIO_OPTIONS}

Respond with a single JSON object: {{"caption": string, "best_time": string, "audio_style": string}}
"""

THUMBNAIL_PROMPT_SYSTEM = """You write a single, vivid, concrete image-generation prompt for a
punchy Instagram Reel cover thumbnail summarizing a fact-check video. Base it only on the
headline claims and conclusion given. Describe composition, mood, and a short 2-4 word bold
text overlay to render directly in the image. No real people's faces, no real logos/brands.
Respond with only the image prompt text, nothing else."""


def _build_context(check_id: str) -> str:
    row = db.fetch_one("SELECT claims_json, conclusion FROM reel_checks WHERE id=?", (check_id,))
    if not row:
        return ""
    claims = json.loads(row["claims_json"]) if row["claims_json"] else []
    headlines = "\n".join(f"- {c['claim']} (verdict: {c['verdict']})" for c in claims)
    conclusion = row["conclusion"] or ""
    return f"Conclusion: {conclusion}\n\nClaims:\n{headlines}"


def generate_caption_kit(check_id: str) -> dict:
    """One LLM call covering caption + posting-time + audio-vibe together --
    all three are just content-strategy text derived from the same claims/
    conclusion context, so there's no reason to split them into separate
    (and separately billed) calls."""
    context = _build_context(check_id)
    client = next_client()
    response = call_with_retry(lambda: client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": KIT_PROMPT},
            {"role": "user", "content": context},
        ],
        response_format={"type": "json_object"},
        temperature=0.5,
    ))
    data = json.loads(response.choices[0].message.content)
    return {
        "caption": data.get("caption", ""),
        "best_time": data.get("best_time", ""),
        "audio_style": data.get("audio_style", ""),
    }


def generate_thumbnail(check_id: str, output_path: Path) -> Path:
    """Drafts an image-generation prompt from the claims/conclusion (via the
    text model already used elsewhere in this app), then renders it with
    OpenAI's image model. Portrait 1024x1536 -- the closest fixed size the
    image API offers to a 9:16 Reels cover -- not pixel-exact, but a usable
    downloadable draft."""
    context = _build_context(check_id)
    groq_client = next_client()
    prompt_response = call_with_retry(lambda: groq_client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": THUMBNAIL_PROMPT_SYSTEM},
            {"role": "user", "content": context},
        ],
        temperature=0.6,
    ))
    image_prompt = prompt_response.choices[0].message.content.strip()

    openai_client = get_openai_client()
    image_response = openai_client.images.generate(
        model="gpt-image-1", prompt=image_prompt, size="1024x1536", n=1,
    )
    b64 = image_response.data[0].b64_json
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(b64))
    return output_path
