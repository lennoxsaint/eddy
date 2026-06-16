"""ffmpeg/ffprobe subprocess runner. Fails loud, receipts every command,
asserts all output paths stay inside the run directory (hard gate)."""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
import time
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Cross-platform H.264 encoder selection. The renderer hardcoded h264_videotoolbox (macOS-only),
# so every Windows/Linux user got a working proxy then no shippable output. Probe what ffmpeg
# actually has and prefer a hardware encoder, falling back to libx264 (software, universal).
_ENCODER_PREFERENCE = ("h264_videotoolbox", "h264_nvenc", "h264_qsv", "libx264")


# HW encoders can be COMPILED INTO ffmpeg (so they list in `-encoders`) yet fail at runtime when the
# matching GPU/driver is absent — notably h264_nvenc on a GPU-less Linux box or CI runner, which dies
# with "Cannot load libcuda.so.1". Listing is not usability: probe these before trusting them.
_PROBED_ENCODERS = ("h264_videotoolbox", "h264_nvenc", "h264_qsv")


def _encoder_works(enc: str) -> bool:
    """True iff ffmpeg can actually RUN this encoder here — a 1-frame, null-muxed test encode of a
    synthetic source succeeds. The only reliable signal that a compiled-in HW encoder has working
    hardware (presence in `-encoders` does not imply a usable GPU/driver)."""
    extra = ["-allow_sw", "1"] if enc == "h264_videotoolbox" else []  # let VT fall back to SW in VMs
    try:
        proc = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "testsrc=size=64x64:rate=1:duration=0.1", "-frames:v", "1",
             "-c:v", enc, *extra, "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        return proc.returncode == 0
    except Exception:
        return False


@functools.lru_cache(maxsize=1)
def _available_encoders() -> frozenset[str]:
    try:
        out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15)
        # encoder names are lowercase [a-z0-9_]; this also excludes the legend lines (" V..... = Video")
        listed = set(re.findall(r"^\s*[A-Z.]{6}\s+([a-z0-9_]+)", out.stdout, re.MULTILINE))
    except Exception:
        return frozenset()
    # Drop any HW encoder that lists but can't actually run, so resolve_video_encoder never picks a
    # dead one (e.g. nvenc without CUDA). libx264 (software) is always trusted as the universal floor.
    for enc in _PROBED_ENCODERS:
        if enc in listed and not _encoder_works(enc):
            listed.discard(enc)
    return frozenset(listed)


def resolve_video_encoder() -> str:
    avail = _available_encoders()
    for enc in _ENCODER_PREFERENCE:
        if enc in avail:
            return enc
    return "libx264"  # present in any full ffmpeg build; safe universal default


def video_encoder_args(bitrate: str = "7000k") -> list[str]:
    """`-c:v ...` args for the resolved encoder, with a uniform yuv420p pixel format for broad
    player compatibility (nvenc/qsv don't always default to it; harmless on videotoolbox/libx264)."""
    enc = resolve_video_encoder()
    if enc == "h264_videotoolbox":
        args = ["-c:v", enc, "-allow_sw", "1", "-b:v", bitrate]
    elif enc == "h264_nvenc":
        args = ["-c:v", enc, "-preset", "p4", "-b:v", bitrate]
    elif enc == "h264_qsv":
        args = ["-c:v", enc, "-b:v", bitrate]
    else:
        args = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    return args + ["-pix_fmt", "yuv420p"]


class FfmpegError(RuntimeError):
    pass


_OUTPUT_EXTS = (".mp4", ".wav", ".jpg", ".jpeg", ".png", ".srt", ".ass", ".vtt", ".mkv", ".m4a", ".mov", ".webp")


def _assert_outputs_inside(argv: list[str], allowed_root: Path | None) -> None:
    if allowed_root is None:
        return
    root = allowed_root.resolve()
    # Check EVERY output path, not just the last (a split/multi-output command would bypass a
    # last-only check), and use is_relative_to over resolved paths — a string `startswith` lets a
    # sibling dir share a prefix (`/runs/ab` vs `/runs/abc`) escape the gate. Inputs (the arg right
    # after -i) are excluded: source footage legitimately lives outside the run dir.
    for j, a in enumerate(argv):
        if not a.endswith(_OUTPUT_EXTS):
            continue
        if j > 0 and argv[j - 1] == "-i":
            continue  # an input, not a write target
        out = Path(a).resolve()
        if not out.is_relative_to(root):
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


def concat_quote(path) -> str:
    """Quote a path for an ffmpeg concat/ffconcat script — NOT shell quoting.

    shlex.quote produces shell-style escaping the concat demuxer cannot parse, so any path
    containing an apostrophe (a very common case) hard-fails the render. The demuxer wraps the
    path in single quotes and writes a literal `'` as `'\\''`.
    """
    return "'" + str(path).replace("'", "'\\''") + "'"


def run_ffprobe(args: list[str], timeout: int = 120) -> str:
    proc = subprocess.run([FFPROBE, "-hide_banner", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe failed: {proc.stderr[-1000:]}")
    return proc.stdout
