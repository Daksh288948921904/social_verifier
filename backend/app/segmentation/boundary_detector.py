import json
import logging
from dataclasses import dataclass

from app.core.config import settings
from app.core.groq_pool import next_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are analyzing one block of a live TV newsroom broadcast transcript,
given as timestamped lines (absolute HH:MM:SS timestamps).

Your job is to split this block into distinct news stories. A new story begins whenever:
- The anchor transitions to a new topic ("moving on to...", "in other news...", "next up...")
- Coverage switches to a different named story, reporter package, or interview subject
- The broadcast cuts to a commercial break (treat the break itself as ending the prior story)

Return every story that is FULLY CONCLUDED within this transcript block as a cut. Do NOT
return the final story if it is still ongoing when the transcript block ends -- leave it
out entirely, it will be re-evaluated once more transcript has arrived in the next block.
If you are unsure whether a story has concluded, leave it out rather than guessing.

You may also be given a list of stories already covered earlier in this session. Use it
only as context: if this block's content is a follow-up/update on one of those stories,
treat it as a new, separate cut here (broadcasts often revisit a story later with new
developments) rather than silently merging it -- just don't re-cut the exact same segment
of transcript that already produced an earlier clip.

Respond with a single JSON object matching this schema exactly:
{
  "cuts": [
    {
      "title": string,
      "summary": string,
      "start_timestamp": "HH:MM:SS",
      "end_timestamp": "HH:MM:SS"
    }
  ]
}
Return cuts in chronological order. Return {"cuts": []} if no story fully concludes in
this block.
"""


@dataclass
class ProposedCut:
    title: str
    summary: str
    start_timestamp: str
    end_timestamp: str


def _parse_response(content: str) -> list[ProposedCut]:
    data = json.loads(content)
    return [
        ProposedCut(
            title=c["title"],
            summary=c.get("summary", ""),
            start_timestamp=c["start_timestamp"],
            end_timestamp=c["end_timestamp"],
        )
        for c in data["cuts"]
    ]


def extract_cuts(
    window_text: str,
    previously_covered: list[str] | None = None,
    retry_on_malformed: bool = True,
) -> list[ProposedCut]:
    """Sends one batch window's worth of transcript (the still-open tail of
    the previous batch, if any, plus everything newly transcribed) to the
    segmentation LLM in a single call and gets back every story that fully
    concluded within it. Batching whole windows like this instead of
    re-checking after every few seconds of new transcript is what keeps this
    call infrequent and cheap on tokens. Returns an empty list (never
    raises) on a malformed response after the retry, so one bad LLM reply
    doesn't stall the session.

    previously_covered is a RAG-retrieved list of titles/summaries of
    earlier clips from this same session (the batches vectors most similar
    to this window), given as context so the model doesn't re-cut a story
    that's already been published, and can recognize when this window is a
    follow-up on earlier coverage rather than a new story."""
    client = next_client()
    user_parts = []
    if previously_covered:
        coverage = "\n".join(f"- {c}" for c in previously_covered)
        user_parts.append(
            "Stories already covered earlier in this session (for context only -- "
            f"do not re-cut these, only recognize follow-ups to them):\n{coverage}"
        )
    user_parts.append(f"Transcript block:\n{window_text}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]

    attempts = 2 if retry_on_malformed else 1
    for attempt in range(attempts):
        response = client.chat.completions.create(
            model=settings.segmentation_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content
        try:
            return _parse_response(content)
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Malformed cut-extraction response (attempt %d): %s", attempt, content)
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": "That response did not match the required JSON schema. Reply with only the JSON object.",
            })

    logger.error("Cut extraction failed after retries; treating this block as having no closed cuts")
    return []
