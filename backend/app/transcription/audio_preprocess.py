import tempfile
from pathlib import Path

from app.core.config import settings
from app.core.proc import run_checked

# highpass: strip sub-80Hz rumble/hum that carries no speech content.
# afftdn: general FFT-based denoiser for broadcast noise floor.
# loudnorm: EBU R128 loudness normalization, evens out anchor-desk vs
#           field-report vs phone-in level jumps.
# acompressor: light dynamic-range compression so quiet speech doesn't sit
#              under the noise floor after normalization.
DSP_FILTER_CHAIN = "highpass=f=80,afftdn,loudnorm,acompressor"


def apply_dsp(input_wav: Path, output_wav: Path, filter_chain: str = DSP_FILTER_CHAIN) -> Path:
    """Runs the DSP filter chain over a raw audio chunk, producing a cleaned
    16kHz mono WAV ready for VAD + Whisper."""
    cmd = [
        settings.ffmpeg_bin,
        "-loglevel", "error",
        "-i", str(input_wav),
        "-af", filter_chain,
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        "-y",
        str(output_wav),
    ]
    run_checked(cmd)
    return output_wav


def concat_wavs(input_wavs: list[Path], output_path: Path) -> Path:
    """Losslessly joins raw PCM WAV chunks -- all sharing the same 16kHz mono
    pcm_s16le format straight off ffmpeg's segment muxer -- into one file, so
    DSP and Whisper each run once per batch window instead of once per small
    capture chunk."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in input_wavs:
            f.write(f"file '{p}'\n")
        list_path = f.name
    try:
        run_checked([
            settings.ffmpeg_bin, "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            "-y", str(output_path),
        ])
    finally:
        Path(list_path).unlink(missing_ok=True)
    return output_path
