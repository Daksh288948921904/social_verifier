import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def cookies_args(cookies_file: str):
    """Yields the yt-dlp CLI args needed to use the given cookies file path,
    or [] if it's empty. Different platforms need different logged-in
    accounts' cookies (e.g. Instagram vs YouTube), so callers pass their own
    settings.*_cookies_file value rather than this reading one global path.

    yt-dlp doesn't just read --cookies, it writes back to the same file at
    the end (to persist any refreshed tokens from the session) -- fails
    outright if that path is read-only, which is exactly how Render mounts
    Secret Files. Copies it into a scratch dir first (cleaned up on exit,
    not left sitting in a persistent data directory -- it's a live session
    credential) and points yt-dlp at the copy."""
    if not cookies_file:
        yield []
        return
    with tempfile.TemporaryDirectory(prefix="ytdlp_cookies_") as tmp:
        writable_cookies = Path(tmp) / "cookies.txt"
        writable_cookies.write_text(_normalize(Path(cookies_file).read_text(errors="replace")))
        writable_cookies.chmod(0o600)
        yield ["--cookies", str(writable_cookies)]


def _normalize(text: str) -> str:
    """Netscape cookie files must be tab-separated, but pasting one into a
    web form (e.g. Render's Secret File editor) often turns the tabs into
    spaces or adds CRLF line endings -- and yt-dlp then rejects the whole
    file. Cookie fields never contain whitespace, so rebuild each 7-field
    line with tabs."""
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        is_cookie = stripped and (not stripped.startswith("#") or stripped.startswith("#HttpOnly_"))
        if is_cookie and "\t" not in stripped:
            fields = stripped.split(None, 6)
            if len(fields) == 7:
                line = "\t".join(fields)
        lines.append(line.rstrip() if not is_cookie else line)
    return "\n".join(lines)
