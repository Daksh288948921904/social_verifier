CHUNK_WORDS = 120
CHUNK_OVERLAP_WORDS = 20


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS, overlap_words: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    """Splits text into overlapping word-count chunks. A claim's quote +
    claim + analysis is usually short enough to be a single chunk; the
    overlap only starts mattering for longer analyses, so later claims can
    still retrieve a coherent slice of an earlier one instead of a
    mid-sentence cutoff."""
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_words:
        return [text.strip()]

    stride = chunk_words - overlap_words
    chunks = []
    for start in range(0, len(words), stride):
        chunk = " ".join(words[start:start + chunk_words])
        chunks.append(chunk)
        if start + chunk_words >= len(words):
            break
    return chunks
