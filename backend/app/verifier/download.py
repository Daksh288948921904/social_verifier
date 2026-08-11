import shutil
import subprocess
import tempfile
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
    Facebook) out of the box; Instagram in particular sometimes serves a
    restricted format list (occasionally video with no audio track at all)
    to requests that look unauthenticated -- see ytdlp_cookies_file."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(dest_dir / "source.%(ext)s")
    cmd = [
        settings.ytdlp_bin,
        # Prefer a single already-combined (non-DASH) format first: Instagram
        # in particular splits video into a separate DASH manifest with
        # individually-fetched video-only and audio-only streams, and the
        # audio-track fetch specifically appears to come back
        # blocked/restricted from this server's IP even though the same
        # merge works fine from a home connection -- confirmed by
        # reproducing it. A plain combined format is one single request with
        # both tracks baked in, sidestepping that entirely. Falls back to
        # the DASH bestvideo+bestaudio merge for sources that don't offer a
        # combined format at all.
        "-f", "best[format_id!*=dash]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
    ]

    with tempfile.TemporaryDirectory(prefix="ytdlp_cookies_") as cookies_tmp:
        if settings.ytdlp_cookies_file:
            # yt-dlp doesn't just read --cookies, it writes back to the same
            # file at the end (to persist any refreshed tokens from the
            # session) -- fails outright if that path is read-only, which is
            # exactly how Render mounts Secret Files. Copy it into a scratch
            # dir first (cleaned up right after this call, not left sitting
            # in the check's persistent data directory -- it's a live
            # session credential) and point yt-dlp at the copy.
            writable_cookies = Path(cookies_tmp) / "cookies.txt"
            shutil.copy(settings.ytdlp_cookies_file, writable_cookies)
            # shutil.copy preserves the source's permission bits too -- a
            # Render Secret File is read-only, and that mode would carry
            # straight over onto this copy otherwise, defeating the point.
            writable_cookies.chmod(0o600)
            cmd += ["--cookies", str(writable_cookies)]
        cmd += ["-o", output_template, "--no-playlist", url]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
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
