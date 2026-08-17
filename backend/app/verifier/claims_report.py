import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.verifier.pdf_text import esc

VERDICT_LABEL = {
    "true": "TRUE", "false": "FALSE", "misleading": "MISLEADING",
    "partially true": "PARTIALLY TRUE", "unverifiable": "UNVERIFIABLE",
}
VERDICT_COLOR = {
    "true": "#0a5c1f", "false": "#b3001e", "misleading": "#b36b00",
    "partially true": "#8a6d00", "unverifiable": "#555555",
}

# A second, independent verdict scoped only to the indexed Indian-government
# source corpus (see app/verifier/claims.py::_verify_against_gov_sources) --
# rendered as its own line, distinct from the main verdict bar above, since
# it's a separate judgment that may disagree with or say less than the
# general fact-check.
GOV_VERDICT_LABEL = {
    "confirmed": "CONFIRMED", "contradicted": "CONTRADICTED",
    "partially confirmed": "PARTIALLY CONFIRMED", "not addressed": "NOT ADDRESSED",
    "no source found": "NO OFFICIAL SOURCE FOUND",
}
GOV_VERDICT_COLOR = {
    "confirmed": "#0a5c1f", "contradicted": "#b3001e",
    "partially confirmed": "#8a6d00", "not addressed": "#555555",
    "no source found": "#888888",
}

_styles = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle("ReportTitle", parent=_styles["Title"], fontSize=20, spaceAfter=4)
_URL_STYLE = ParagraphStyle(
    "URL", parent=_styles["BodyText"], fontSize=9,
    textColor=colors.HexColor("#666666"), spaceAfter=10,
)
_CONCLUSION_HEADER_STYLE = ParagraphStyle("ConclusionHeader", parent=_styles["Heading2"], fontSize=13, spaceAfter=4)
_CONCLUSION_STYLE = ParagraphStyle("Conclusion", parent=_styles["BodyText"], fontSize=11, leading=15, spaceAfter=14)
_VERDICT_BAR_STYLE = ParagraphStyle(
    "VerdictBar", parent=_styles["BodyText"], fontSize=10,
    fontName="Helvetica-Bold", textColor=colors.white,
)
_CLAIM_STATEMENT_STYLE = ParagraphStyle(
    "ClaimStatement", parent=_styles["BodyText"], fontSize=11.5, leading=15,
    fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=3,
)
_META_STYLE = ParagraphStyle("Meta", parent=_styles["BodyText"], fontSize=9, textColor=colors.HexColor("#777777"))
_QUOTE_STYLE = ParagraphStyle(
    "Quote", parent=_styles["BodyText"], fontSize=10.5, leading=14,
    fontName="Helvetica-Oblique", textColor=colors.HexColor("#333333"), spaceBefore=3, spaceAfter=6,
)
_ANALYSIS_STYLE = ParagraphStyle("Analysis", parent=_styles["BodyText"], fontSize=10.5, leading=14.5, spaceAfter=4)
_SOURCE_STYLE = ParagraphStyle(
    "Source", parent=_styles["BodyText"], fontSize=9, leading=12.5,
    textColor=colors.HexColor("#0a4a8f"), spaceBefore=6,
)
_OFFICIAL_SOURCE_STYLE = ParagraphStyle(
    "OfficialSource", parent=_styles["BodyText"], fontSize=9, leading=12.5,
    fontName="Helvetica-Bold", textColor=colors.HexColor("#0a5c1f"), spaceBefore=3,
)
_GOV_VERDICT_STYLE = ParagraphStyle(
    "GovVerdict", parent=_styles["BodyText"], fontSize=9.5, leading=13, spaceBefore=6,
)


def _verdict_bar(verdict: str, index: int) -> Table:
    label = VERDICT_LABEL.get(verdict, esc(verdict.upper()))
    color = VERDICT_COLOR.get(verdict, "#333333")
    bar = Table(
        [[Paragraph(f"CLAIM {index + 1} &mdash; {label}", _VERDICT_BAR_STYLE)]],
        colWidths=[6.4 * inch],
    )
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color)),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return bar


def _gov_verdict_line(official_verdict: str, official_analysis: str) -> Paragraph:
    label = GOV_VERDICT_LABEL.get(official_verdict, esc(official_verdict.upper()))
    color = GOV_VERDICT_COLOR.get(official_verdict, "#555555")
    text = f'<font color="{color}"><b>Govt. Source Verdict: {esc(label)}</b></font>'
    if official_analysis:
        text += f" — {esc(official_analysis)}"
    return Paragraph(text, _GOV_VERDICT_STYLE)


def render_pdf(url: str, claims: list[dict], conclusion: str) -> bytes:
    """Renders every verified claim for one reel check -- quote, timestamp,
    full analysis, and sources -- into a single downloadable PDF. Unlike the
    debunk script, this needs no LLM call (the data is already sitting in
    reel_checks.claims_json/conclusion), so it's built fresh on every
    request rather than cached to disk."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=LETTER,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch,
    )

    flow = [
        Paragraph("Fact-Check Report", _TITLE_STYLE),
        Paragraph(esc(url), _URL_STYLE),
    ]

    if conclusion:
        flow.append(Paragraph("Conclusion", _CONCLUSION_HEADER_STYLE))
        flow.append(Paragraph(esc(conclusion), _CONCLUSION_STYLE))

    flow.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc"), thickness=1))
    flow.append(Spacer(1, 10))

    for i, claim in enumerate(claims):
        flow.append(_verdict_bar(claim["verdict"], i))
        flow.append(Paragraph(esc(claim["claim"]), _CLAIM_STATEMENT_STYLE))
        if claim.get("timestamp"):
            flow.append(Paragraph(esc(claim["timestamp"]), _META_STYLE))
        flow.append(Paragraph(f'“{esc(claim["quote"])}”', _QUOTE_STYLE))

        for para in claim["analysis"].split("\n"):
            para = para.strip()
            if para:
                flow.append(Paragraph(esc(para), _ANALYSIS_STYLE))

        if claim.get("sources"):
            sources = "; ".join(esc(s) for s in claim["sources"])
            flow.append(Paragraph(f"Sources: {sources}", _SOURCE_STYLE))

        if claim.get("official_sources"):
            official = "; ".join(esc(s) for s in claim["official_sources"])
            flow.append(Paragraph(
                f"Verified against official Indian government sources: {official}",
                _OFFICIAL_SOURCE_STYLE,
            ))

        flow.append(_gov_verdict_line(
            claim.get("official_verdict", "no source found"), claim.get("official_analysis", ""),
        ))

        flow.append(Spacer(1, 16))

    doc.build(flow)
    return buffer.getvalue()
