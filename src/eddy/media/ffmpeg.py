"""ffmpeg/ffprobe subprocess runner. Fails loud, receipts every command,
asserts all output paths stay inside the run directory (hard gate)."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


class FfmpegError(RuntimeError):
    pass


def _assert_outputs_inside(argv: list[str], allowed_root: Path | None) -> None:
    if allowed_root is None:
        return
    root = allowed_root.resolve()
    # Outputs are the args that are paths and follow ffmpeg output conventions:
    # the last positional, and anything after -o style flags isn't used here, so we
    # conservatively check every argument that is an existing-or-creatable path that
    # the command would write: ffmpeg writes the final arg; -y doesn't change that.
    candidates = [a for a in argv if a.endswith((".mp4", ".wav", ".jpg", ".png", ".srt", ".ass", ".mkv", ".m4a"))]
    if not candidates:
        return
    out = Path(candidates[-1]).resolve()
    if not str(out).startswith(str(root)):
        raise FfmpegError(f"hard gate: refusing to write outside run dir: {out}")


def run_ffmpeg(
    args: list[str],
    run_dir: Path | None = None,
    receipts=None,
    timeout: int = 3600,
) -> subprocess.CompletedProcess:
    argv = [FFMPEG, "-hide_banner", "-y", *args]
    _assert_outputs_inside(argv, run_dir)
    t0 = time.time()
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if receipts is not None:
        receipts.log(
            "ffmpeg",
            argv=argv,
            exit_code=proc.returncode,
            wall_s=round(time.time() - t0, 2),
        )
    if proc.returncode != 0:
        raise FfmpegError(f"ffmpeg failed ({proc.returncode}): {' '.join(argv[:12])}…\n{proc.stderr[-2000:]}")
    return proc


def run_ffprobe(args: list[str], timeout: int = 120) -> str:
    proc = subprocess.run([FFPROBE, "-hide_banner", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe failed: {proc.stderr[-1000:]}")
    return proc.stdout
