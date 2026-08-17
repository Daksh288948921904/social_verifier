import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.core.config import settings


@contextmanager
def cookies_args():
    """Yields the yt-dlp CLI args needed to use settings.ytdlp_cookies_file,
    or [] if none is configured. yt-dlp doesn't just read --cookies, it
    writes back to the same file at the end (to persist any refreshed
    tokens from the session) -- fails outright if that path is read-only,
    which is exactly how Render mounts Secret Files. Copies it into a
    scratch dir first (cleaned up on exit, not left sitting in a persistent
    data directory -- it's a live session credential) and points yt-dlp at
    the copy."""
    if not settings.ytdlp_cookies_file:
        yield []
        return
    with tempfile.TemporaryDirectory(prefix="ytdlp_cookies_") as tmp:
        writable_cookies = Path(tmp) / "cookies.txt"
        shutil.copy(settings.ytdlp_cookies_file, writable_cookies)
        # shutil.copy preserves the source's permission bits too -- a Render
        # Secret File is read-only, and that mode would carry straight over
        # onto this copy otherwise, defeating the point.
        writable_cookies.chmod(0o600)
        yield ["--cookies", str(writable_cookies)]
