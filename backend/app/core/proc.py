import subprocess


def run_checked(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run(..., check=True) raises CalledProcessError whose
    default str() is just "Command [...] returned non-zero exit status N" --
    it captures stdout/stderr but doesn't include them in the message, so
    every failure this app has hit in production has shown up as a
    genuinely unhelpful, cause-free error with no way to diagnose it short
    of reproducing it locally. This re-raises with the actual stderr
    included."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    try:
        return subprocess.run(cmd, check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(
            f"Command failed (exit {e.returncode}): {' '.join(cmd)}\n{stderr}"
        ) from e
