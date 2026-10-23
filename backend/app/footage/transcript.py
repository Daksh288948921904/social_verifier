import html
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from xml.etree import ElementTree

import httpx

from app.core import db
from app.core.config import settings
from app.core.ytdlp_cookies import cookies_args

logger = logging.getLogger(__name__)

LINE_SECONDS = 15.0  # caption cues are merged into lines of roughly this length
CAPTION_RETRY_DELAYS = (4.0, 12.0)  # seconds to back off after a 429 from YouTube


@dataclass
class VideoTranscript:
    duration_seconds: float | None = None
    channel: str = ""
    chapters: list[dict] = field(default_factory=list)  # [{start, end, title}]
    lines: list[dict] = field(default_factory=list)  # [{start, end, text}]
    # True when the video *has* a caption track but downloading it failed
    # (e.g. YouTube rate-limiting) -- as opposed to a video with none.
    incomplete: bool = False


def get_transcript(video_id: str) -> VideoTranscript:
    """Caption text plus duration/chapters for one YouTube video, cached in
    footage_transcripts -- the same video often turns up under several
    keywords of one project (and across projects), and captions never change
    once published, so it's only ever fetched once. A video with no captions
    at all is cached too (with empty lines), so it isn't retried every time."""
    row = db.fetch_one("SELECT * FROM footage_transcripts WHERE video_id=?", (video_id,))
    if row:
        return VideoTranscript(
            duration_seconds=row["duration_seconds"],
            channel=row["channel"],
            chapters=json.loads(row["chapters_json"]),
            lines=json.loads(row["lines_json"]),
        )

    transcript = _fetch(video_id)
    # A failed fetch (no metadata, or a caption track that wouldn't
    # download) is most likely a transient block (429/bot check), not a
    # captionless video -- don't cache that, so a later run can try again.
    if transcript.duration_seconds is not None and not transcript.incomplete:
        db.execute(
            "INSERT INTO footage_transcripts "
            "(video_id, duration_seconds, channel, chapters_json, lines_json) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(video_id) DO NOTHING",
            (
                video_id, transcript.duration_seconds, transcript.channel,
                json.dumps(transcript.chapters), json.dumps(transcript.lines),
            ),
        )
    return transcript


def _fetch(video_id: str) -> VideoTranscript:
    info = _fetch_info(video_id)
    if info is None:
        return VideoTranscript()
    transcript = VideoTranscript(
        duration_seconds=info.get("duration"),
        channel=info.get("channel") or info.get("uploader") or "",
        chapters=[
            {"start": c.get("start_time", 0), "end": c.get("end_time", 0), "title": c.get("title", "")}
            for c in info.get("chapters") or []
        ],
    )
    caption_url = _pick_caption_url(info)
    if caption_url:
        try:
            transcript.lines = _srv1_to_lines(_download_caption(caption_url))
        except (httpx.HTTPError, ElementTree.ParseError) as e:
            logger.warning("Caption download failed for %s: %s", video_id, e)
            transcript.incomplete = True
    return transcript


def _download_caption(url: str) -> str:
    """YouTube answers bursts of caption requests (several keywords running
    side by side) with 429s that clear within seconds -- back off and retry
    rather than treating the video as captionless."""
    for delay in (*CAPTION_RETRY_DELAYS, None):
        resp = httpx.get(url, timeout=90)
        if resp.status_code == 429 and delay is not None:
            time.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.text
    raise AssertionError("unreachable")


def _fetch_info(video_id: str) -> dict | None:
    cmd = [
        settings.ytdlp_bin, "-J", "--skip-download", "--ignore-no-formats-error",
        "--no-warnings", "--no-playlist",
    ]
    with cookies_args(settings.ytdlp_youtube_cookies_file) as cookie_args:
        try:
            result = subprocess.run(
                [*cmd, *cookie_args, f"https://www.youtube.com/watch?v={video_id}"],
                capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Timed out fetching info for %s", video_id)
            return None
    if result.returncode != 0:
        logger.warning("yt-dlp failed for %s: %s", video_id, result.stderr.strip()[-500:])
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _pick_caption_url(info: dict) -> str | None:
    """One English track, best first: human-written captions, then YouTube's
    own speech recognition of English speech ("en-orig", or regional ones
    like "en-US-orig"), then its machine translation of a non-English video
    ("en" in automatic_captions is a translation whenever no English
    original exists) -- still good enough to match against an English
    script, but YouTube rate-limits translation requests far harder, so it's
    strictly the last resort. srv1 is by far the smallest format
    (~9x smaller than json3), which matters because YouTube streams a
    track's first fetch slowly (~13KB/s observed)."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    manual_en = sorted(lang for lang in manual if lang == "en" or lang.startswith("en-"))
    candidates = [manual[lang] for lang in manual_en]
    auto_orig = sorted(
        (lang for lang in auto if lang.startswith("en") and lang.endswith("-orig")),
        key=lambda lang: lang != "en-orig",
    )
    candidates += [auto[lang] for lang in auto_orig]
    if "en" in auto:
        candidates.append(auto["en"])
    for formats in candidates:
        for fmt in formats:
            if fmt.get("ext") == "srv1" and fmt.get("url"):
                return fmt["url"]
    return None


def _srv1_to_lines(xml_text: str) -> list[dict]:
    """Flattens srv1 caption cues (<text start=".." dur="..">) into
    ~LINE_SECONDS-long lines. Raw auto-caption cues are a few words each,
    which would make the transcript far longer (in tokens) than its actual
    content without telling the matcher anything more."""
    lines: list[dict] = []
    current: dict | None = None
    for node in ElementTree.fromstring(xml_text).iter("text"):
        text = html.unescape(" ".join((node.text or "").split()))
        if not text:
            continue
        start = float(node.get("start", 0))
        end = start + float(node.get("dur", 0))
        if current is None or start - current["start"] >= LINE_SECONDS:
            current = {"start": round(start, 1), "end": round(end, 1), "text": text}
            lines.append(current)
        else:
            current["text"] = f"{current['text']} {text}"
            current["end"] = round(max(current["end"], end), 1)
    return lines
