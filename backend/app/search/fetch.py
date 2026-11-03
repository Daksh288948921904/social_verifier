import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.ytdlp_cookies import cookies_args


class DownloadError(RuntimeError):
    pass


def cookies_for_source(source: str) -> str:
    if source == "instagram":
        return settings.ytdlp_cookies_file
    if source == "youtube":
        return settings.ytdlp_youtube_cookies_file
    return ""


def download_clip(url: str, dest_dir: Path, cookies_file: str = "") -> Path:
    """Downloads whatever video is at `url` as a single local file via
    yt-dlp. Separate from app/verifier/download.py's download_clip(), which
    is specific to the reel-check pipeline (always uses the Instagram
    cookies file regardless of source, and requires an audio track since
    fact-checking needs a transcript) -- search results have neither of
    those constraints."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(dest_dir / "source.%(ext)s")
    cmd = [
        settings.ytdlp_bin,
        # Prefer a single already-combined (non-DASH) format first -- see
        # app/verifier/download.py for why (Instagram's DASH audio stream
        # can come back blocked from a datacenter IP).
        "-f", "best[format_id!*=dash]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
    ]

    with cookies_args(cookies_file) as cookie_args:
        cmd += cookie_args
        cmd += ["-o", output_template, "--no-playlist", url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise DownloadError(f"yt-dlp failed to download {url}: {result.stderr.strip()}")

    matches = sorted(dest_dir.glob("source.*"))
    if not matches:
        raise DownloadError(f"yt-dlp reported success but produced no file for {url}")
    return matches[0]


def download_range(url: str, start: float, end: float, dest: Path, cookies_file: str = "") -> Path:
    """Fetches just [start, end] of whatever video is at `url` (YouTube,
    Instagram, ...) rather than the whole thing. Keyframes are forced at the
    cut points so the clip starts on the exact frame asked for."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        settings.ytdlp_bin, "--no-warnings", "--no-playlist",
        # 720p is plenty and keeps the re-encode at the cut points quick; the
        # combined non-DASH format comes first for the same reason as above.
        "-f", "bv*[height<=720]+ba/b[height<=720]/best[format_id!*=dash]/bv*+ba/b",
        "--download-sections", f"*{start:.2f}-{end:.2f}",
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(dest.with_suffix(".%(ext)s")),
    ]
    with cookies_args(cookies_file) as cookie_args:
        try:
            result = subprocess.run([*cmd, *cookie_args, url], capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            raise DownloadError("The download timed out after 10 minutes")
    if result.returncode != 0 or not dest.exists():
        lines = [l for l in result.stderr.splitlines() if "ERROR" in l] or result.stderr.splitlines()
        raise DownloadError(lines[-1] if lines else "yt-dlp produced no file")
    return dest
