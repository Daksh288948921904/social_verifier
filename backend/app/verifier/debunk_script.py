import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core import db
from app.core.config import settings
from app.core.groq_pool import call_with_retry, next_client

VERDICT_LABEL = {
    "true": "TRUE", "false": "FALSE", "misleading": "MISLEADING",
    "partially true": "PARTIALLY TRUE", "unverifiable": "UNVERIFIABLE",
}

SCRIPT_PROMPT = """You are a scriptwriter helping an Indian fact-checker cut a debunk Reel that
splices together, claim by claim: (1) the original clip of the claim as it was actually said, then
(2) the creator's own to-camera reaction video fact-checking that specific claim. This is NOT a
new standalone reel -- it reuses the exact original clip for each claim, so do not write any
narration for the clip beats. You are only writing the creator's own on-camera reaction script for
each claim.

You are given a numbered list of claims with their real quote, real verdict, and the real
fact-check reasoning. For EACH claim, in the same order, write what the creator should say on
camera reacting to that specific claim -- funny, in a casual Hinglish tone Indian Reels audiences
love (self-aware WhatsApp-University jokes, "arre bhai" style mock-shock, deadpan delivery before
a reveal) -- while staying 100% factually consistent with that claim's real verdict and reasoning.
Never invent or soften a verdict for comedic effect, and never mock any real named individual's
appearance or identity -- the joke always targets the claim/misinformation itself, not a person.

Where it fits naturally, have the creator ask the audience a short direct question for engagement
(e.g. "Sounds legit, right? ... Wrong.") -- put this in its own field, not forced into every claim.

Respond as a single JSON object:
{
  "title": short punchy working title for the compiled video,
  "intro_hook": 1-2 lines the creator says to camera before the first clip, to stop the scroll,
  "reactions": [
    {
      "claim_index": the claim's index as given (0-based, matching the input order),
      "reaction_narration": what the creator says on camera reacting to and fact-checking THIS
                            claim, ending with the true verdict stated plainly,
      "humor_cue": a specific comedic direction for this reaction (e.g. "beat pause, then
                   deadpan: ...", "cut to exaggerated shocked face"), or null if this one claim's
                   reaction is played straight with no joke,
      "question_cue": a short direct-to-camera question to the audience for engagement if one
                      fits naturally here, or null
    }
  ],
  "outro_cta": the closing line to camera encouraging shares/follows
}

Include exactly one "reactions" entry per claim given, in the same order, matching claim_index.
"""


def _load_claims(check_id: str) -> tuple[list[dict], str]:
    row = db.fetch_one("SELECT claims_json, conclusion FROM reel_checks WHERE id=?", (check_id,))
    if not row:
        return [], ""
    claims = json.loads(row["claims_json"]) if row["claims_json"] else []
    return claims, row["conclusion"] or ""


def _build_context(claims: list[dict], conclusion: str) -> str:
    numbered = "\n".join(
        f"{i}. Claim: {c['claim']}\n   Quote: \"{c['quote']}\"\n   Verdict: {c['verdict']}\n"
        f"   Reasoning: {c['analysis'][:300]}"
        for i, c in enumerate(claims)
    )
    return f"Conclusion: {conclusion}\n\nClaims:\n{numbered}"


def generate_script(check_id: str) -> dict:
    claims, conclusion = _load_claims(check_id)
    context = _build_context(claims, conclusion)

    client = next_client()
    response = call_with_retry(lambda: client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": SCRIPT_PROMPT},
            {"role": "user", "content": context},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    ))
    data = json.loads(response.choices[0].message.content)
    reactions_by_index = {r.get("claim_index"): r for r in data.get("reactions", [])}

    beats = []
    for i, claim in enumerate(claims):
        r = reactions_by_index.get(i, {})
        beats.append({
            "claim_index": i,
            "claim_quote": claim["quote"],
            "verdict": claim["verdict"],
            "reaction_narration": r.get("reaction_narration", ""),
            "humor_cue": r.get("humor_cue"),
            "question_cue": r.get("question_cue"),
        })

    return {
        "title": data.get("title", "Debunk Reel Script"),
        "intro_hook": data.get("intro_hook", ""),
        "beats": beats,
        "outro_cta": data.get("outro_cta", ""),
    }


_styles = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle("ScriptTitle", parent=_styles["Title"], fontSize=22, spaceAfter=4)
_HOOK_STYLE = ParagraphStyle(
    "Hook", parent=_styles["BodyText"], fontSize=13, leading=17,
    textColor=colors.HexColor("#b3001e"), fontName="Helvetica-Bold", spaceAfter=12,
)
_CLIP_LABEL_STYLE = ParagraphStyle(
    "ClipLabel", parent=_styles["BodyText"], fontSize=10, fontName="Helvetica-Bold",
    textColor=colors.white, alignment=TA_LEFT,
)
_REACTION_LABEL_STYLE = ParagraphStyle(
    "ReactionLabel", parent=_styles["BodyText"], fontSize=10, fontName="Helvetica-Bold",
    textColor=colors.white, alignment=TA_LEFT,
)
_QUOTE_STYLE = ParagraphStyle(
    "Quote", parent=_styles["BodyText"], fontSize=10.5, leading=14,
    textColor=colors.HexColor("#333333"), fontName="Helvetica-Oblique",
)
_VERDICT_STYLE = ParagraphStyle(
    "Verdict", parent=_styles["BodyText"], fontSize=9.5, leading=12,
    fontName="Helvetica-Bold", textColor=colors.HexColor("#b3001e"),
)
_NARRATION_STYLE = ParagraphStyle(
    "Narration", parent=_styles["BodyText"], fontSize=11.5, leading=15, spaceAfter=4,
)
_HUMOR_STYLE = ParagraphStyle(
    "Humor", parent=_styles["BodyText"], fontSize=10.5, leading=14,
    textColor=colors.HexColor("#7a4a00"), fontName="Helvetica-BoldOblique",
)
_QUESTION_STYLE = ParagraphStyle(
    "Question", parent=_styles["BodyText"], fontSize=10.5, leading=14,
    textColor=colors.HexColor("#0a4a8f"), fontName="Helvetica-BoldOblique",
)
_CTA_STYLE = ParagraphStyle(
    "CTA", parent=_styles["BodyText"], fontSize=12, leading=16,
    fontName="Helvetica-Bold", textColor=colors.HexColor("#0a5c1f"), spaceBefore=14,
)


def _labeled_bar(text: str, style: ParagraphStyle, bg_hex: str) -> Table:
    bar = Table([[Paragraph(text, style)]], colWidths=[6.4 * inch])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_hex)),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return bar


def render_pdf(script: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=LETTER,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch,
    )
    flow = [
        Paragraph(script["title"], _TITLE_STYLE),
        Paragraph(f'"{script["intro_hook"]}"', _HOOK_STYLE),
        HRFlowable(width="100%", color=colors.HexColor("#cccccc"), thickness=1),
        Spacer(1, 10),
    ]

    for beat in script["beats"]:
        verdict_label = VERDICT_LABEL.get(beat["verdict"], beat["verdict"].upper())

        flow.append(_labeled_bar(
            f'ORIGINAL CLIP -- CLAIM {beat["claim_index"] + 1}', _CLIP_LABEL_STYLE, "#1a1a1a",
        ))
        flow.append(Spacer(1, 4))
        flow.append(Paragraph(f'“{beat["claim_quote"]}”', _QUOTE_STYLE))
        flow.append(Paragraph(f"Verdict: {verdict_label}", _VERDICT_STYLE))
        flow.append(Spacer(1, 8))

        flow.append(_labeled_bar("YOUR REACTION VIDEO", _REACTION_LABEL_STYLE, "#7a1010"))
        flow.append(Spacer(1, 4))
        flow.append(Paragraph(beat["reaction_narration"], _NARRATION_STYLE))
        if beat.get("humor_cue"):
            flow.append(Paragraph(f"HUMOR CUE: {beat['humor_cue']}", _HUMOR_STYLE))
        if beat.get("question_cue"):
            flow.append(Paragraph(f"ASK THE AUDIENCE: {beat['question_cue']}", _QUESTION_STYLE))
        flow.append(Spacer(1, 14))

    flow.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc"), thickness=1))
    flow.append(Paragraph(script["outro_cta"], _CTA_STYLE))

    doc.build(flow)
    return output_path
