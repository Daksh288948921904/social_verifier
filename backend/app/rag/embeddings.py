import hashlib
import math
import re

# Groq (this app's only configured AI provider) advertises an embeddings
# endpoint in its SDK, but `nomic-embed-text-v1_5` isn't actually enabled on
# this account (confirmed: absent from client.models.list(), and calling it
# 404s). Rather than add a second provider just for vectors, embeddings are
# computed locally via feature hashing -- no network call, no model
# download, no per-session vocabulary to build up first.
DIMENSIONS = 256
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _token_bucket(token: str) -> tuple[int, float]:
    # blake2b instead of Python's built-in hash(): str hashing is
    # randomized per-process (PYTHONHASHSEED) for security, which would
    # make embeddings incomparable across a backend restart.
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    index = int.from_bytes(digest[:4], "big") % DIMENSIONS
    sign = 1.0 if digest[4] & 1 else -1.0
    return index, sign


def embed_text(text: str) -> list[float]:
    """Hashing-trick bag-of-words embedding: each distinct token is hashed
    into one of DIMENSIONS buckets (with a hashed sign to reduce collision
    bias), weighted by log-dampened term frequency, then L2-normalized.
    Coarser than a neural embedding model -- it matches on shared
    vocabulary, not deeper meaning -- but is good enough to retrieve
    "earlier clips that talked about similar things" for RAG context, with
    zero external dependencies."""
    counts: dict[str, int] = {}
    for tok in _TOKEN_RE.findall(text.lower()):
        counts[tok] = counts.get(tok, 0) + 1

    vector = [0.0] * DIMENSIONS
    for tok, count in counts.items():
        index, sign = _token_bucket(tok)
        vector[index] += sign * math.log1p(count)

    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [embed_text(t) for t in texts]
