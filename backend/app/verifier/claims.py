import json
import logging
import re
import time
from dataclasses import asdict, dataclass

from app.core.config import settings
from app.core.groq_pool import call_with_retry as _call_groq_with_retry
from app.core.groq_pool import next_client
from app.core.openai_client import get_client as get_openai_client

logger = logging.getLogger(__name__)

CLAIM_MODEL = settings.segmentation_model
VERIFICATION_MODEL = settings.verification_model

CLAIM_EXTRACTION_PROMPT = """You are a rigorous fact-checking analyst. You are given the full
manuscript (transcript) of a short social media video, with timestamps.

Identify every distinct factual claim made in the video -- anything asserted as true that could
be checked against reality (statistics, events, quotes attributed to people, historical facts,
scientific claims, predictions stated as fact, etc.). Do not include pure opinions, jokes, or
purely subjective statements as claims.

For each claim, quote the EXACT line(s) from the manuscript verbatim (character-for-character,
without the leading timestamp), and separately state the specific, checkable claim being made in
clear terms.

Respond with a single JSON object:
{
  "claims": [
    {
      "quote": string,      // exact verbatim line(s) from the manuscript, without the leading
                             // "[HH:MM:SS]" prefix
      "timestamp": string,  // the "HH:MM:SS" timestamp this quote starts at
      "claim": string       // the specific, checkable factual claim being made
    }
  ]
}
Be thorough -- do not skip claims because they seem minor or because there are many. List every
checkable claim made in the video.
"""

VERIFICATION_PROMPT_TEMPLATE = """You are a rigorous, in-depth fact-checker. Research the
following claim thoroughly using web search before answering -- do not rely only on prior
knowledge, since claims in viral social videos are often recent, misleadingly framed, or present
outdated information as current.

Claim to verify: "{claim}"
Exact quote from the source video: "{quote}"

Respond with ONLY a single JSON object, no other text, no markdown code fences, matching this
schema exactly:
{{"verdict": "true" | "false" | "misleading" | "partially true" | "unverifiable",
  "analysis": string,
  "sources": [string]}}

The analysis field is the most important part: give a thorough, detailed explanation covering
what is accurate, what is missing context, and what is misleadingly framed even if technically
true. Do not give a superficial one-line answer -- do not skip nuance for brevity. Populate
sources with the URLs or named sources your search actually found.
"""

FALLBACK_VERIFICATION_SYSTEM_PROMPT = """You are a fact-checking analyst assessing a claim using
only your own training knowledge -- you do NOT have live web search available right now, so you
cannot verify anything that happened recently or check current facts. Be explicit about this
limitation in your analysis, and mark the verdict as "unverifiable" whenever the claim depends on
information you cannot be confident is still current or accurate from memory alone.

Respond with a single JSON object:
{
  "verdict": "true" | "false" | "misleading" | "partially true" | "unverifiable",
  "analysis": string,  // Explain your reasoning in depth, and explicitly flag that this was NOT
                       // checked against live sources -- it reflects only the model's training
                       // knowledge, which may be outdated or incomplete.
  "sources": []
}
"""

WEB_SEARCH_RETRY_DELAYS = (3.0, 8.0)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass
class ExtractedClaim:
    quote: str
    timestamp: str
    claim: str
    # Precise boundaries for cutting a downloadable clip of the exact quote,
    # filled in by clip_match.attach_clip_times() after extraction (matched
    # against real Whisper segment timing, not just this LLM-reported
    # timestamp) -- 0.0 until then.
    start_seconds: float = 0.0
    end_seconds: float = 0.0


@dataclass
class ClaimVerification:
    quote: str
    timestamp: str
    claim: str
    verdict: str
    analysis: str
    sources: list[str]
    grounded: bool  # True if checked via live web search, False if fallen back to a plain model
    start_seconds: float = 0.0
    end_seconds: float = 0.0


def extract_claims(manuscript: str) -> list[ExtractedClaim]:
    if not manuscript.strip():
        return []
    client = next_client()
    response = _call_groq_with_retry(lambda: client.chat.completions.create(
        model=CLAIM_MODEL,
        messages=[
            {"role": "system", "content": CLAIM_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Manuscript:\n{manuscript}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    ))
    try:
        data = json.loads(response.choices[0].message.content)
        return [
            ExtractedClaim(quote=c["quote"], timestamp=c.get("timestamp", ""), claim=c["claim"])
            for c in data.get("claims", [])
        ]
    except (json.JSONDecodeError, TypeError, KeyError):
        logger.exception("Malformed claim-extraction response")
        return []


def _parse_verification(content: str) -> tuple[str, str, list[str]]:
    data = json.loads(_FENCE_RE.sub("", content.strip()))
    verdict = data.get("verdict", "unverifiable")
    analysis = data["analysis"]
    sources = data.get("sources") or []
    return verdict, analysis, sources


def _verify_via_web_search(claim: ExtractedClaim) -> tuple[str, str, list[str]] | None:
    """Uses OpenAI's web-search-enabled Responses API for real, grounded
    fact-checking. Retries a couple of times on transient errors before
    giving up (returns None, never raises) so the caller can fall back to
    a plain-model verdict instead of failing the whole claim."""
    try:
        client = get_openai_client()
    except RuntimeError:
        logger.warning("OPENAI_API_KEY not configured; skipping web-search verification")
        return None

    prompt = VERIFICATION_PROMPT_TEMPLATE.format(claim=claim.claim, quote=claim.quote)
    for attempt, delay in enumerate((0.0, *WEB_SEARCH_RETRY_DELAYS)):
        if delay:
            time.sleep(delay)
        try:
            response = client.responses.create(
                model=VERIFICATION_MODEL,
                tools=[{"type": "web_search"}],
                input=prompt,
            )
            return _parse_verification(response.output_text)
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("OpenAI verification returned malformed JSON on attempt %d", attempt + 1)
        except Exception as e:
            logger.warning("OpenAI verification attempt %d failed: %s", attempt + 1, e)
    return None


def _verify_via_plain_model(claim: ExtractedClaim) -> tuple[str, str, list[str]]:
    client = next_client()
    user_content = f'Claim to verify: "{claim.claim}"\n\nExact quote from the source video: "{claim.quote}"'
    response = _call_groq_with_retry(lambda: client.chat.completions.create(
        model=CLAIM_MODEL,
        messages=[
            {"role": "system", "content": FALLBACK_VERIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    ))
    try:
        return _parse_verification(response.choices[0].message.content)
    except (json.JSONDecodeError, TypeError, KeyError):
        logger.exception("Malformed fallback-verification response")
        return (
            "unverifiable",
            "The fact-checking model returned a malformed response for this claim.",
            [],
        )


def verify_claim(claim: ExtractedClaim) -> ClaimVerification:
    grounded_result = _verify_via_web_search(claim)
    if grounded_result is not None:
        verdict, analysis, sources = grounded_result
        return ClaimVerification(
            quote=claim.quote, timestamp=claim.timestamp, claim=claim.claim,
            verdict=verdict, analysis=analysis, sources=sources, grounded=True,
            start_seconds=claim.start_seconds, end_seconds=claim.end_seconds,
        )

    logger.warning("Falling back to non-web-search verification for claim: %r", claim.claim)
    verdict, analysis, sources = _verify_via_plain_model(claim)
    analysis = (
        "[Not web-verified -- the live fact-check search was unavailable, this reflects only "
        f"the model's training knowledge.] {analysis}"
    )
    return ClaimVerification(
        quote=claim.quote, timestamp=claim.timestamp, claim=claim.claim,
        verdict=verdict, analysis=analysis, sources=sources, grounded=False,
        start_seconds=claim.start_seconds, end_seconds=claim.end_seconds,
    )


def verify_claim_to_dict(v: ClaimVerification) -> dict:
    return asdict(v)


CONCLUSION_PROMPT = """You are a rigorous fact-checking editor. You are given every factual claim
made in a short video, each already fact-checked with a verdict and a detailed analysis.

Write a concise overall conclusion (3-6 sentences) summarizing the fact-check findings for the
whole video: what topic(s) it covers, the overall pattern across the claims (e.g. mostly false,
mostly accurate, a mix of true and misleading), and the single most important takeaway a reader
should walk away with. Name the most significant false or misleading claims specifically rather
than speaking only in generalities -- but do not simply restate every claim one by one; synthesize
the overall picture.

Respond with only the conclusion text -- no headers, no markdown, no JSON.
"""


def _fallback_conclusion(claims: list[ClaimVerification]) -> str:
    """A tallied, non-LLM summary used when the conclusion model is
    unreachable (e.g. the shared daily Groq quota is exhausted even after
    a retry) -- every claim was already verified in depth at this point,
    so a failure here shouldn't discard that work or the whole check."""
    counts: dict[str, int] = {}
    for c in claims:
        counts[c.verdict] = counts.get(c.verdict, 0) + 1
    tally = ", ".join(f"{n} {v}" for v, n in counts.items())
    return (
        f"{len(claims)} claim(s) were checked in this clip ({tally}). The automatic summary "
        "step is temporarily unavailable, but every individual claim's verdict and full "
        "analysis below are complete."
    )


def generate_conclusion(claims: list[ClaimVerification]) -> str:
    """Synthesizes a top-of-report summary across every already-verified
    claim. Runs after per-claim verification, on the plain (non-web-search)
    model -- all the grounding already happened per claim, this step is
    pure synthesis of analyses that already exist."""
    if not claims:
        return "No checkable factual claims were found in this clip."

    claims_input = "\n\n".join(
        f"Claim: {c.claim}\nVerdict: {c.verdict}\nAnalysis: {c.analysis}" for c in claims
    )
    client = next_client()
    try:
        response = _call_groq_with_retry(lambda: client.chat.completions.create(
            model=CLAIM_MODEL,
            messages=[
                {"role": "system", "content": CONCLUSION_PROMPT},
                {"role": "user", "content": f"Fact-checked claims:\n\n{claims_input}"},
            ],
            temperature=0.3,
        ))
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("Conclusion generation failed even after retry; using a tallied fallback")
        return _fallback_conclusion(claims)
