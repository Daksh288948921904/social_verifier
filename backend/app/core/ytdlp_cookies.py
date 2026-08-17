import shutil
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
        shutil.copy(cookies_file, writable_cookies)
        # shutil.copy preserves the source's permission bits too -- a Render
        # Secret File is read-only, and that mode would carry straight over
        # onto this copy otherwise, defeating the point.
        writable_cookies.chmod(0o600)
        yield ["--cookies", str(writable_cookies)]
