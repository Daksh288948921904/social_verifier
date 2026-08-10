from pathlib import Path

from app.core.config import settings
from app.core.proc import run_checked

# Portrait canvas matching typical reel/short dimensions -- every input clip
# is scaled/padded onto this common canvas before concatenation, since a
# claim clip cut from the checked reel and a user's own uploaded video are
# not guaranteed to share a resolution, aspect ratio, or codec.
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
FPS = 30


def compile_timeline(clip_paths: list[Path], output_path: Path) -> Path:
    """Concatenates already-resolved clip paths into one output video.
    Uses ffmpeg's concat *filter* (not the concat demuxer) specifically
    because it decodes and re-encodes each input, which is what makes
    mixing heterogeneous sources (different resolutions/codecs/frame
    rates) safe -- the demuxer only works when every input already shares
    the same codec parameters."""
    if not clip_paths:
        raise ValueError("Nothing to compile: the timeline is empty.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    n = len(clip_paths)

    cmd = [settings.ffmpeg_bin, "-loglevel", "error", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]

    filter_parts = []
    concat_inputs = []
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale=w={CANVAS_WIDTH}:h={CANVAS_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={CANVAS_WIDTH}:{CANVAS_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}[v{i}]"
        )
        filter_parts.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]")
        concat_inputs.append(f"[v{i}][a{i}]")
    filter_parts.append(f"{''.join(concat_inputs)}concat=n={n}:v=1:a=1[outv][outa]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-c:a", "aac",
        str(output_path),
    ]
    run_checked(cmd)
    return output_path
