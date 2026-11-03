import re

import httpx

_KEY_RE = re.compile(r"([?&]key=)[^&\s']+")


def redact(text: str) -> str:
    """Strips API keys out of anything that might reach the UI or the logs --
    httpx errors quote the full request URL, key included."""
    return _KEY_RE.sub(r"\1***", text)


def raise_for_google_error(resp: httpx.Response, service: str) -> None:
    """Raises a readable error for a failed Google API call, using Google's
    own explanation from the response body -- never the request URL, which
    carries the API key."""
    if resp.is_success:
        return
    try:
        err = resp.json().get("error") or {}
    except ValueError:
        err = {}
    message = str(err.get("message") or resp.reason_phrase)
    reasons = {e.get("reason") for e in err.get("errors") or [] if isinstance(e, dict)}
    if reasons & {"quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded"} or resp.status_code == 429:
        raise RuntimeError(
            f"{service}: the API key's daily quota is used up (it resets at midnight Pacific time)."
        )
    if "does not have the access to Custom Search JSON API" in message:
        raise RuntimeError(
            f"{service}: this API key's Google Cloud project has no access to the Custom Search "
            "JSON API -- Google has closed it to projects that weren't already using it."
        )
    raise RuntimeError(f"{service}: {redact(message)} (HTTP {resp.status_code})")
