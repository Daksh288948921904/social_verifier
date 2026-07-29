import subprocess
from pathlib import Path

from app.core.config import settings


class DownloadError(RuntimeError):
    pass


def download_clip(url: str, dest_dir: Path) -> Path:
    """Downloads a short social clip (reel/short/etc.) as a single file via
    yt-dlp. Unlike the live-capture pipeline, this is a one-shot finite
    download of a short video -- no segmenting, no continuous re-resolution.
    yt-dlp supports most platforms (YouTube Shorts, TikTok, X/Twitter,
    Facebook) out of the box; Instagram in particular sometimes needs a
    logged-in cookie file to reliably resolve, which isn't configured here,
    so an Instagram link may fail without one."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(dest_dir / "source.%(ext)s")
    result = subprocess.run(
        [settings.ytdlp_bin, "-f", "best", "-o", output_template, "--no-playlist", url],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise DownloadError(f"yt-dlp failed to download {url}: {result.stderr.strip()}")
    matches = sorted(dest_dir.glob("source.*"))
    if not matches:
        raise DownloadError(f"yt-dlp reported success but produced no file for {url}")
    return matches[0]


def extract_audio(video_path: Path, output_path: Path) -> Path:
    subprocess.run(
        [
            settings.ffmpeg_bin, "-loglevel", "error", "-y",
            "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            str(output_path),
        ],
        check=True, capture_output=True, text=True,
    )
    return output_path
