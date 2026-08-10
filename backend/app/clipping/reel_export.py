import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core import db
from app.core.config import settings
from app.core.groq_pool import call_with_retry, next_client
from app.core.proc import run_checked

HOOK_PROMPT = """You are packaging a news clip as a vertical Reel for social media. You are given
the clip's title and summary. Produce two things:

1. "hook": a short (3-6 word) punchy headline to display as a title card over the first 2 seconds
   of the Reel -- the kind of text that stops someone scrolling. Must stay factually accurate to
   the title/summary given, no exaggeration or invented details.
2. "audio_style": a short description of the mood/genre/pacing of background audio that would suit
   this clip (e.g. "tense, staccato instrumental" or "measured news-tempo percussion"), labeled as
   a commonly-used style for this kind of content -- NOT a claim about what's currently trending,
   since you have no access to live trending-audio data. End by telling the user to pick an actual
   trending sound matching this vibe from Instagram's own audio picker when they post.

Respond as a single JSON object: {"hook": string, "audio_style": string}
"""


def generate_hook_and_style(clip_id: str) -> dict:
    row = db.fetch_one("SELECT title, summary FROM clips WHERE id=?", (clip_id,))
    context = f"Title: {row['title']}\nSummary: {row['summary']}"

    client = next_client()
    response = call_with_retry(lambda: client.chat.completions.create(
        model=settings.segmentation_model,
        messages=[
            {"role": "system", "content": HOOK_PROMPT},
            {"role": "user", "content": context},
        ],
        response_format={"type": "json_object"},
        temperature=0.6,
    ))
    data = json.loads(response.choices[0].message.content)
    return {
        "hook": data.get("hook", row["title"]),
        "audio_style": data.get("audio_style", ""),
    }


# Candidate bold font files across the environments this actually runs in --
# macOS locally, Debian in the production container (fonts-dejavu-core, see
# Dockerfile). First one found on disk wins; PIL's bitmap default is the last
# resort so text rendering never crashes even with no TTF installed at all.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

CANVAS_W = 1080
CANVAS_H = 1920


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_text_block(
    draw: ImageDraw.ImageDraw, text: str, *, font_size: int, center_y: int, max_width: int,
) -> None:
    """Draws one word-wrapped, boxed text block onto an already-open PIL
    ImageDraw canvas -- factored out so a single frame can carry both the
    hook and a caption at once when their windows overlap."""
    font = _load_font(font_size)
    lines = _wrap_text(draw, text, font, max_width)
    line_height = font_size + 14
    block_height = line_height * len(lines)
    top = center_y - block_height // 2

    padding_x, padding_y = 36, 20
    widths = [draw.textbbox((0, 0), line, font=font)[2] for line in lines]
    box_width = min(max_width + padding_x * 2, max(widths, default=0) + padding_x * 2)
    box_left = (CANVAS_W - box_width) // 2
    draw.rounded_rectangle(
        [box_left, top - padding_y, box_left + box_width, top + block_height + padding_y],
        radius=10, fill=(0, 0, 0, 165),
    )
    for i, line in enumerate(lines):
        line_width = draw.textbbox((0, 0), line, font=font)[2]
        x = (CANVAS_W - line_width) // 2
        y = top + i * line_height
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))


def _render_frame(active: list[tuple[str, str]], output_path: Path) -> Path:
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for kind, text in active:
        if kind == "hook":
            _draw_text_block(draw, text, font_size=68, center_y=220, max_width=940)
        else:
            _draw_text_block(draw, text, font_size=48, center_y=CANVAS_H - 260, max_width=900)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    return output_path


def _merge_intervals(
    events: list[tuple[float, float, str, str]], clip_duration: float,
) -> list[tuple[float, float, list[tuple[str, str]]]]:
    """Turns a list of (start, end, kind, text) events -- which can overlap
    (e.g. the hook and a caption both active at once) -- into a sequence of
    non-overlapping intervals covering [0, clip_duration] with no gaps, each
    tagged with whichever events are active during it."""
    boundaries = {0.0, clip_duration}
    for s, e, _, _ in events:
        boundaries.add(max(0.0, min(s, clip_duration)))
        boundaries.add(max(0.0, min(e, clip_duration)))
    points = sorted(boundaries)

    intervals = []
    for t1, t2 in zip(points, points[1:]):
        if t2 <= t1:
            continue
        active = [(kind, text) for s, e, kind, text in events if s <= t1 < e]
        intervals.append((t1, t2, active))
    return intervals


OVERLAY_FPS = 5  # plenty for text that only changes every few seconds


def build_overlay_track(clip_id: str, hook_text: str, work_dir: Path) -> Path:
    """Figures out the hook title card (first 2s) and each transcript
    segment overlapping this clip as a caption (segment-level granularity,
    ~10s chunks, since that's what the live transcription pipeline currently
    captures, not word-by-word bursts), merges overlapping windows into
    non-overlapping intervals covering the whole clip with no gaps, and lays
    them out as a numbered PNG sequence (hardlinked, not copied, from a
    small set of distinct rendered frames -- most intervals repeat the same
    "blank" or single-caption frame) at OVERLAY_FPS.

    This went through two broken attempts first: ffmpeg's concat *demuxer*
    silently ignores per-image `duration` directives (confirmed via ffprobe:
    a requested 1.9s slice produced 0.04s of output), and chaining `-loop 1
    -t <duration>` inputs through the concat *filter* produced bizarre,
    inconsistent results in this environment (sub-second output some runs,
    a hung multi-minute render others) that didn't trace back to any single
    fixable cause. A plain numbered image sequence read via `-framerate` is
    the most standard, well-tested way to turn stills into video in ffmpeg,
    and sidesteps all of it."""
    clip = db.fetch_one(
        "SELECT session_id, start_seconds, end_seconds FROM clips WHERE id=?", (clip_id,)
    )
    clip_duration = clip["end_seconds"] - clip["start_seconds"]

    segments = db.fetch_all(
        "SELECT absolute_start, absolute_end, text FROM transcript_segments "
        "WHERE session_id=? AND absolute_end > ? AND absolute_start < ? ORDER BY absolute_start",
        (clip["session_id"], clip["start_seconds"], clip["end_seconds"]),
    )

    events: list[tuple[float, float, str, str]] = [(0.0, 2.0, "hook", hook_text)]
    for seg in segments:
        rel_start = max(0.0, seg["absolute_start"] - clip["start_seconds"])
        rel_end = min(clip_duration, seg["absolute_end"] - clip["start_seconds"])
        text = seg["text"].strip().replace("\n", " ")
        if rel_end > rel_start and text:
            events.append((rel_start, rel_end, "caption", text))

    intervals = _merge_intervals(events, clip_duration)

    frame_cache: dict[tuple, Path] = {}
    seq_dir = work_dir / "seq"
    seq_dir.mkdir(parents=True, exist_ok=True)
    total_frames = max(1, round(clip_duration * OVERLAY_FPS))
    width = len(str(total_frames))

    frame_index = 0
    for t1, t2, active in intervals:
        key = tuple(active)
        if key not in frame_cache:
            frame_cache[key] = _render_frame(active, work_dir / f"frame_{len(frame_cache)}.png")
        source_png = frame_cache[key]

        n_frames = max(1, round((t2 - t1) * OVERLAY_FPS))
        for _ in range(n_frames):
            if frame_index >= total_frames:
                break
            frame_index += 1
            dest = seq_dir / f"{frame_index:0{width}d}.png"
            dest.hardlink_to(source_png)

    # Pad out to total_frames if rounding left it short, by repeating the
    # last rendered frame.
    last_source = frame_cache[tuple(intervals[-1][2])] if intervals else None
    while frame_index < total_frames and last_source is not None:
        frame_index += 1
        (seq_dir / f"{frame_index:0{width}d}.png").hardlink_to(last_source)

    return seq_dir / f"%0{width}d.png"


def render_reel(clip_video_path: Path, overlay_seq_pattern: Path, output_path: Path) -> Path:
    """Crops/pads the clip to a 1080x1920 portrait canvas (blurred, scaled
    copy of the source filling the background rather than a hard center-crop
    that could cut someone out of frame), then composites the hook/caption
    overlay -- a numbered PNG sequence read via -framerate -- on top in one
    pass."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        # Clips cut via stream-copy trim (see clipping/cutter.py) keep their
        # original stream's PTS rather than resetting to 0 -- this one's
        # first frame is timestamped ~2.9s in, for instance. Left alone, that
        # offsets the whole video against the overlay track (which starts
        # cleanly at 0), silently eating the first couple of seconds of
        # overlay content -- long enough to make a 2s hook title card never
        # appear at all, while barely denting longer caption windows (which
        # is what made this so confusing to track down).
        "[0:v]setpts=PTS-STARTPTS,"
        # gblur's cost scales with both sigma and pixel count -- at full
        # 1080x1920 resolution, sigma=30 alone was taking 30+ minutes per
        # clip. Blurring a heavily downscaled copy and scaling it back up
        # gives a visually identical soft background (blur output is
        # inherently low-frequency) at a fraction of the compute cost.
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,scale=108:192,boxblur=8:2,scale=1080:1920[bg];"
        "[0:v]setpts=PTS-STARTPTS,"
        "scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        "[base][1:v]overlay=0:0[v]"
    )

    run_checked([
        settings.ffmpeg_bin, "-loglevel", "error",
        "-i", str(clip_video_path),
        "-framerate", str(OVERLAY_FPS), "-i", str(overlay_seq_pattern),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac",
        "-y", str(output_path),
    ])
    return output_path
