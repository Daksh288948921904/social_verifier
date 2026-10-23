import itertools
import logging
import re
import threading
import time
from typing import Callable, TypeVar

from groq import Groq, RateLimitError

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cycle: itertools.cycle | None = None
_clients: dict[str, Groq] = {}

T = TypeVar("T")

_RETRY_AFTER_RE = re.compile(r"try again in (?:([\d.]+)m)?([\d.]+)s")
RATE_LIMIT_MAX_WAIT_SECONDS = 600.0  # don't block a background job forever


def _get_cycle():
    global _cycle
    if _cycle is None:
        keys = settings.groq_api_keys
        if not keys:
            raise RuntimeError(
                "No Groq API keys configured (set GROQ_API_KEY in backend/.env)"
            )
        _cycle = itertools.cycle(keys)
    return _cycle


def next_client() -> Groq:
    """Round-robins across all configured Groq API keys so continuous
    per-chunk transcription + boundary-detection calls spread across
    multiple keys' rate limits instead of hammering a single one."""
    with _lock:
        key = next(_get_cycle())
        client = _clients.get(key)
        if client is None:
            client = Groq(api_key=key)
            _clients[key] = client
        return client


def _parse_retry_after(message: str) -> float | None:
    match = _RETRY_AFTER_RE.search(message)
    if not match:
        return None
    minutes = float(match.group(1)) if match.group(1) else 0.0
    seconds = float(match.group(2))
    return minutes * 60 + seconds


def call_rotating(fn: Callable[[Groq], T]) -> T:
    """Like call_with_retry, but a rate-limited key moves on to the next key
    straight away instead of waiting. Each key has its own daily token cap,
    so one exhausted key (a multi-minute wait) says nothing about the others.
    Only once every key has been tried does it fall back to waiting it out."""
    attempts = len(settings.groq_api_keys)
    for _ in range(attempts - 1):
        try:
            return fn(next_client())
        except RateLimitError as e:
            logger.warning("Groq key rate-limited (%s); trying the next key", _parse_retry_after(str(e)))
    return call_with_retry(lambda: fn(next_client()))


def call_with_retry(fn: Callable[[], T]) -> T:
    """Groq's on-demand tier has a small daily token budget shared across
    every feature in this app (live sessions, reel checks, newspapers,
    Instagram kits), so hitting it mid-pipeline is common and shouldn't
    blow away an otherwise-successful run. Groq's 429 for this case reports
    how long until it clears (e.g. "try again in 8m15s") -- if that's a
    bounded wait, sleep it out and retry once instead of failing outright."""
    try:
        return fn()
    except RateLimitError as e:
        wait = _parse_retry_after(str(e))
        if wait is None or wait > RATE_LIMIT_MAX_WAIT_SECONDS:
            raise
        logger.warning("Groq rate limit hit; waiting %.0fs before retrying", wait)
        time.sleep(wait + 2.0)
        return fn()
