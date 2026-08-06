from xml.sax.saxutils import escape


def esc(text: str) -> str:
    """Escapes text for safe embedding in a reportlab Paragraph, which uses a
    small XML-like markup parser -- unescaped &, <, > in claim/LLM text (e.g.
    "AT&T", "5 < 10") silently corrupt the parsed text runs instead of
    raising, producing garbled/overlapping glyphs. Must wrap every dynamic
    string before it reaches Paragraph()."""
    return escape(text or "")
