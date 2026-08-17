import subprocess
from abc import ABC, abstractmethod

from app.core.config import settings
from app.core.ytdlp_cookies import cookies_args


class StreamResolutionError(RuntimeError):
    pass


class StreamSource(ABC):
    """Resolves a user-provided URL to a concrete, ffmpeg-consumable input URL."""

    needs_periodic_reresolution: bool = False

    # Total duration of the underlying media in seconds, if known and finite
    # (a VOD, or a broadcast that has already ended). None means unbounded/
    # unknown -- a genuinely still-live broadcast -- so the capture
    # supervisor must never treat "connection dropped" as "reached the end"
    # for it, and must never seek into a freshly re-resolved URL (a live
    # manifest's own timeline starts near "now", not at our capture offset).
    total_duration_seconds: float | None = None

    @abstractmethod
    def get_input_url(self) -> str:
        ...


class DirectUrlSource(StreamSource):
    """A raw HLS (.m3u8) or RTMP URL, usable by ffmpeg as-is."""

    needs_periodic_reresolution = False

    def __init__(self, url: str):
        self.url = url

    def get_input_url(self) -> str:
        return self.url


class YouTubeLiveSource(StreamSource):
    """A YouTube Live watch URL, resolved to a playable HLS manifest via yt-dlp.

    The resolved manifest URL is signed and expires, so callers must re-invoke
    get_input_url() to refresh it whenever ffmpeg's read starts failing.
    """

    needs_periodic_reresolution = True

    def __init__(self, watch_url: str, format_selector: str = "best"):
        self.watch_url = watch_url
        self.format_selector = format_selector
        self.total_duration_seconds = self._probe_duration()

    def _probe_duration(self) -> float | None:
        """yt-dlp reports a finite `duration` for VODs and for broadcasts
        that have already ended, and an empty/"NA" value for a genuinely
        ongoing live stream. A failed probe is treated the same as "unknown"
        (None) rather than raising, since this only gates an optimization
        (clean stop + resume-seek) -- worst case without it is the old
        restart-forever-from-zero behavior, not a crash."""
        try:
            with cookies_args() as cookie_args:
                result = subprocess.run(
                    [settings.ytdlp_bin, "--no-warnings", *cookie_args, "--print", "duration", self.watch_url],
                    capture_output=True, text=True, timeout=30,
                )
            return float(result.stdout.strip())
        except (subprocess.SubprocessError, OSError, ValueError):
            return None

    def get_input_url(self) -> str:
        with cookies_args() as cookie_args:
            result = subprocess.run(
                [settings.ytdlp_bin, "-g", "-f", self.format_selector, *cookie_args, self.watch_url],
                capture_output=True,
                text=True,
                timeout=30,
            )
        if result.returncode != 0:
            raise StreamResolutionError(
                f"yt-dlp failed to resolve {self.watch_url}: {result.stderr.strip()}"
            )
        # yt-dlp may print multiple URLs (one per stream) if -f didn't merge
        # audio+video into a single HLS variant; take the first non-empty line.
        urls = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not urls:
            raise StreamResolutionError(
                f"yt-dlp returned no resolvable URL for {self.watch_url}"
            )
        return urls[0]


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def resolve_source(url: str) -> StreamSource:
    if is_youtube_url(url):
        return YouTubeLiveSource(url)
    return DirectUrlSource(url)
