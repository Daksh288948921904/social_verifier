import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.proc import run_checked


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
        [
            settings.ytdlp_bin,
            # "-f best" picks the single best *pre-merged* format, which for
            # some sources is a video-only stream with no audio track at
            # all -- yt-dlp warns about exactly this. bestvideo+bestaudio
            # downloads both and lets yt-dlp mux them (via ffmpeg, already
            # a dependency here); the /best fallback covers sources that
            # only ever offer a single combined format to begin with.
            "-f", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "-o", output_template, "--no-playlist", url,
        ],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise DownloadError(f"yt-dlp failed to download {url}: {result.stderr.strip()}")
    matches = sorted(dest_dir.glob("source.*"))
    if not matches:
        raise DownloadError(f"yt-dlp reported success but produced no file for {url}")

    video_path = matches[0]
    if not _has_audio_stream(video_path):
        # Confirmed locally that bestvideo+bestaudio correctly merges both
        # tracks for URLs that fail this way in production -- so a missing
        # audio track here means the *download* silently came back
        # video-only in this specific environment (most likely the
        # audio-track request being blocked/rate-limited for this server's
        # IP; some platforms treat datacenter/cloud egress IPs differently
        # than residential ones), not a bug in the format selection logic.
        # Failing clearly here beats a cryptic ffmpeg crash three steps
        # later in extract_audio.
        raise DownloadError(
            f"Downloaded video for {url} has no audio track (video-only download). "
            "This can happen when the source platform serves a different/restricted "
            "set of formats to this server than to a regular browser -- there's "
            "nothing to fact-check without audio to transcribe."
        )
    return video_path


def _has_audio_stream(video_path: Path) -> bool:
    result = subprocess.run(
        [
            settings.ffprobe_bin, "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(video_path),
        ],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def extract_audio(video_path: Path, output_path: Path) -> Path:
    run_checked([
        settings.ffmpeg_bin, "-loglevel", "error", "-y",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(output_path),
    ])
    return output_path
