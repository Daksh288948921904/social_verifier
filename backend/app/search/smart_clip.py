"""Smart clip: find a short, *clean* stretch of a YouTube video -- footage an
editor can drop straight into a package, with no news ticker, channel logo,
watermark, burned-in captions or lower-third on screen -- and cut just that.

Footage's matcher works from transcripts, but tickers and logos are only
visible in the picture, so this looks at frames. Frames are grabbed straight
from the stream with ffmpeg (no full download), tiled into labelled contact
sheets, and judged by a vision model on Groq:

  1. Scan: ~24 frames spread across the video -> which are clean, and how
     well each fits the search keyword.
  2. Place: around the best clean frames, find shot changes with ffmpeg's
     scene detection and fit the 8-10s window inside one continuous shot.
  3. Verify: check 3 frames *inside* that exact window, so a logo or
     caption that pops in mid-clip is caught.
  4. Cut that window with yt-dlp (app/footage/clips.download_section).
"""
import base64
import concurrent.futures
import io
import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.core.groq_pool import call_rotating
from app.core.ytdlp_cookies import cookies_args

logger = logging.getLogger(__name__)

MIN_SECONDS, MAX_SECONDS = 8, 10
SCAN_FRAMES = 24
SHEET_COLUMNS, SHEET_ROWS = 4, 3  # 12 frames per contact sheet
TILE_WIDTH = 400  # px per frame on a sheet: enough to read a ticker or a corner logo
MAX_CANDIDATES = 4  # clean frames to verify before giving up
# A hard cut scores high on one frame; a quick dissolve spreads its score
# over a few. Fast motion alone (timelapse traffic) reaches ~0.2.
CUT_SCORE = 0.3  # one frame's ffmpeg scene score that counts as a cut
DISSOLVE_SCORE = 0.45  # ...or the sum over 3 consecutive frames
VERIFY_FRAMES = 3  # the vision model takes at most 3 images per request
SCAN_LIMIT_SECONDS = 3600  # only scan the first hour of very long videos

CLEAN_RULES = """A frame is CLEAN only if the picture is free of ALL of these:
- news ticker / crawl / scrolling text bar
- channel or network logo / bug / watermark (any corner, even small or faint)
- lower-third name strap, caption box, headline banner, "BREAKING"/"LIVE" tags
- burned-in subtitles or any other overlaid text or graphics
- split screen, picture-in-picture, a studio anchor or presenter talking to camera
- a title card, end screen, black or blurry frame
Text that is physically part of the scene (a street sign, a placard someone holds) is fine."""

SCAN_PROMPT = """You are a video editor's assistant. This contact sheet shows separate frames from
one YouTube video, tiled in a grid. The yellow "#n m:ss" tag on the black strip above each frame
was added by us to number it -- it is NOT part of the footage, and the grid itself is not a split
screen. Judge each frame on its own.
The editor needs clean B-roll for this search: "{keyword}".

{rules}

For EVERY frame, report whether it is clean, what (if anything) is overlaid, how well it
fits the search (0-10), and a few words on what it shows.

Respond with JSON only:
{{"frames": [{{"n": 1, "clean": true, "issues": [], "relevance": 7, "shows": "..."}}]}}"""

VERIFY_PROMPT = """The {count} images are separate frames, in order, from one {seconds}-second stretch
of a video an editor wants to use as clean B-roll for: "{keyword}".

{rules}

Is EVERY frame clean? Respond with JSON only:
{{"all_clean": true, "issues": ["..."], "shows": "one sentence describing the shot"}}"""


class SmartClipError(RuntimeError):
    pass


@dataclass
class SmartPick:
    start: float
    end: float
    shows: str
    checked: int  # how many frames were looked at in total
    single_shot: bool  # no cut inside the window


def _video_stream(video_id: str) -> tuple[str, float, str]:
    """(direct stream URL of a <=480p video-only format, duration, title).
    480p is plenty to spot a ticker or a corner logo, and small to seek."""
    with cookies_args(settings.ytdlp_youtube_cookies_file) as cookie_args:
        result = subprocess.run(
            [settings.ytdlp_bin, *cookie_args, "-J", "--no-warnings", "--no-playlist",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=120,
        )
    if result.returncode != 0:
        lines = [l for l in result.stderr.splitlines() if "ERROR" in l] or result.stderr.splitlines()
        # "ERROR: [youtube] abc123XYZ_-: This live event will begin in 9 hours." -> the reason only
        reason = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?([\w-]{11}:\s*)?", "", lines[-1]) if lines else ""
        raise SmartClipError(reason or "Couldn't read the video")
    info = json.loads(result.stdout)
    if info.get("is_live"):
        raise SmartClipError("This is a live stream -- there's no fixed footage to clip yet")
    duration = float(info.get("duration") or 0)
    if duration < MIN_SECONDS + 2:
        raise SmartClipError(f"The video is only {duration:.0f}s long")
    video_only = [
        f for f in info.get("formats") or []
        if f.get("vcodec") not in (None, "none") and f.get("acodec") in (None, "none")
        and f.get("url") and str(f.get("protocol", "")).startswith("http")
        and 0 < (f.get("height") or 0) <= 480
    ]
    if not video_only:
        raise SmartClipError("No suitable video stream found")
    best = max(video_only, key=lambda f: (f.get("height") or 0, f.get("ext") == "mp4"))
    return best["url"], duration, info.get("title") or ""


def _grab_frames(stream_url: str, times: list[float]) -> list[Image.Image | None]:
    """One ffmpeg seek per timestamp, a few in parallel. A frame that fails
    comes back as None rather than sinking the whole scan."""
    def grab(t: float) -> Image.Image | None:
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", stream_url,
                 "-frames:v", "1", "-vf", f"scale={TILE_WIDTH}:-2", tmp.name],
                capture_output=True, timeout=60,
            )
            if r.returncode != 0:
                return None
            try:
                return Image.open(tmp.name).convert("RGB")
            except OSError:
                return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(grab, times))


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        try:
            return ImageFont.load_default(size)
        except TypeError:
            return ImageFont.load_default()


def _contact_sheet(frames: list[tuple[int, float, Image.Image]], columns: int) -> str:
    """Tiles frames into one JPEG with a "#n m:ss" tag in each corner and
    returns it base64-encoded. The tag sits on its own black strip above the
    picture, so it can't be mistaken for an overlay in the footage itself."""
    gap = 8  # black gutter, so neighbouring frames don't read as one split-screen picture
    tile_w = TILE_WIDTH + gap
    tile_h = max(img.height for *_, img in frames)
    label_h = 26
    rows = -(-len(frames) // columns)
    sheet = Image.new("RGB", (columns * tile_w, rows * (tile_h + label_h + gap)), "black")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for i, (n, t, img) in enumerate(frames):
        x, y = (i % columns) * tile_w, (i // columns) * (tile_h + label_h + gap)
        draw.text((x + 6, y + 3), f"#{n}  {int(t // 60)}:{int(t % 60):02d}", fill="yellow", font=font)
        sheet.paste(img, (x, y + label_h))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _jpeg_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _ask(prompt: str, images_b64: list[str]) -> dict:
    response = call_rotating(lambda client: client.chat.completions.create(
        model=settings.vision_model,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            *({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in images_b64),
        ]}],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_completion_tokens=4000,
    ))
    try:
        return json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {}


def _window(t: float, seconds: float, duration: float) -> tuple[float, float]:
    """A `seconds`-long window around t, kept inside the video."""
    start = max(0.0, min(t - seconds / 2, duration - seconds - 0.5))
    return round(start, 1), round(start + seconds, 1)


_SCORE_RE = re.compile(r"pts_time:([\d.]+)\s*\n.*?scene_score=([\d.]+)")


def _shot_cuts(stream_url: str, start: float, end: float) -> list[float]:
    """Times of cuts and quick dissolves between start and end, from
    ffmpeg's per-frame scene score. Decodes only that stretch, small."""
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", stream_url,
         "-an", "-vf", "scale=160:-2,select='gte(scene,0)',metadata=print:key=lavfi.scene_score",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    scores = [(start + float(t), float(sc)) for t, sc in _SCORE_RE.findall(r.stderr)]
    cuts: list[float] = []
    for i, (t, sc) in enumerate(scores):
        window = sum(x for _, x in scores[i:i + 3])
        if (sc >= CUT_SCORE or window >= DISSOLVE_SCORE) and (not cuts or t - cuts[-1] > 1.0):
            cuts.append(t)
    return cuts


def _place(stream_url: str, t: float, seconds: float, duration: float) -> tuple[float, float, bool]:
    """Fits the clip inside the continuous shot that contains t: (start, end,
    single_shot). Falls back to a plain window around t when that shot is
    shorter than MIN_SECONDS."""
    lo, hi = max(0.0, t - MAX_SECONDS - 1), min(duration - 0.5, t + MAX_SECONDS + 1)
    cuts = _shot_cuts(stream_url, lo, hi)
    shot_start = max([c for c in cuts if c <= t], default=lo)
    shot_end = min([c for c in cuts if c > t], default=hi)
    # Stay a few frames clear of the cut itself.
    shot_start, shot_end = shot_start + 0.2, shot_end - 0.2
    length = shot_end - shot_start
    if length >= seconds:
        start = min(max(t - seconds / 2, shot_start), shot_end - seconds)
        return round(start, 1), round(start + seconds, 1), True
    if length >= MIN_SECONDS:
        return round(shot_start, 1), round(shot_end, 1), True
    start, end = _window(t, seconds, duration)
    return start, end, False


def find_clean_clip(video_id: str, keyword: str, seconds: float = MAX_SECONDS) -> SmartPick:
    seconds = max(MIN_SECONDS, min(MAX_SECONDS, seconds))
    stream_url, duration, _title = _video_stream(video_id)

    # 1. Scan. Skip the first/last few percent (intros, logos, end screens).
    span_end = min(duration, SCAN_LIMIT_SECONDS)
    lo, hi = span_end * 0.03, span_end * 0.97
    count = max(4, min(SCAN_FRAMES, int((hi - lo) // 3)))
    times = [lo + (hi - lo) * (i + 0.5) / count for i in range(count)]
    images = _grab_frames(stream_url, times)
    frames = [(n, t, img) for n, (t, img) in enumerate(zip(times, images), start=1) if img is not None]
    if not frames:
        raise SmartClipError("Couldn't grab any frames from the video")

    verdicts: dict[int, dict] = {}
    per_sheet = SHEET_COLUMNS * SHEET_ROWS
    for i in range(0, len(frames), per_sheet):
        sheet = _contact_sheet(frames[i:i + per_sheet], SHEET_COLUMNS)
        data = _ask(SCAN_PROMPT.format(keyword=keyword, rules=CLEAN_RULES), [sheet])
        for v in data.get("frames") or []:
            try:
                verdicts[int(v.get("n"))] = v
            except (TypeError, ValueError):
                continue

    time_of = {n: t for n, t, _ in frames}
    clean = [
        (n, v) for n, v in verdicts.items()
        if n in time_of and v.get("clean") is True and not v.get("issues")
    ]
    if not clean:
        raise SmartClipError(
            "No clean footage found -- every frame checked had a ticker, logo, captions or other on-screen text"
        )

    def relevance(v: dict) -> float:
        try:
            return float(v.get("relevance") or 0)
        except (TypeError, ValueError):
            return 0.0

    # A clean frame whose neighbours are clean too is more likely to sit in
    # a clean shot, so that breaks ties between equally relevant frames.
    clean_ns = {n for n, _ in clean}
    ranked = sorted(
        clean,
        key=lambda nv: (relevance(nv[1]), (nv[0] - 1 in clean_ns) + (nv[0] + 1 in clean_ns)),
        reverse=True,
    )

    # 2-3. Place each candidate inside its shot and verify that window, best
    # first. A clean window that spans a cut is kept as a fallback in case
    # no single-shot one turns up.
    checked = len(frames)
    rejected: list[str] = []
    fallback: SmartPick | None = None
    for n, v in ranked[:MAX_CANDIDATES]:
        start, end, single_shot = _place(stream_url, time_of[n], seconds, duration)
        inside = [start + 0.4, (start + end) / 2, end - 0.4][:VERIFY_FRAMES]
        imgs = [img for img in _grab_frames(stream_url, inside) if img is not None]
        checked += len(imgs)
        if len(imgs) < 2:
            continue
        check = _ask(
            VERIFY_PROMPT.format(count=len(imgs), seconds=round(end - start), keyword=keyword, rules=CLEAN_RULES),
            [_jpeg_b64(img) for img in imgs],
        )
        if check.get("all_clean") is not True:
            rejected += [str(x) for x in check.get("issues") or []]
            continue
        pick = SmartPick(
            start=start, end=end, shows=str(check.get("shows") or v.get("shows") or "").strip(),
            checked=checked, single_shot=single_shot,
        )
        if single_shot:
            return pick
        fallback = fallback or pick
    if fallback:
        return fallback

    reason = f" ({'; '.join(sorted(set(rejected))[:3])})" if rejected else ""
    raise SmartClipError(
        f"Found clean frames, but no full {int(seconds)}s stretch stayed clean{reason}"
    )
