import math
from array import array

from app.core import db


def _pack(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def _unpack(blob: bytes) -> list[float]:
    return array("f", blob).tolist()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def add_clip(clip_id: str, session_id: str, embedding: list[float], text: str) -> None:
    db.execute(
        "INSERT OR REPLACE INTO clip_embeddings (clip_id, session_id, embedding, text) "
        "VALUES (?, ?, ?, ?)",
        (clip_id, session_id, _pack(embedding), text),
    )


def search(session_id: str, query_embedding: list[float], top_k: int = 5) -> list[tuple[str, float, str]]:
    """Brute-force cosine similarity over one session's stored clip
    embeddings. Fine at this scale -- a session realistically holds dozens,
    not millions, of clips -- so there's no need for a dedicated vector
    index/service, just a couple hundred dot products in Python."""
    rows = db.fetch_all(
        "SELECT clip_id, embedding, text FROM clip_embeddings WHERE session_id=?",
        (session_id,),
    )
    scored = [
        (row["clip_id"], _cosine(query_embedding, _unpack(row["embedding"])), row["text"])
        for row in rows
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:top_k]
