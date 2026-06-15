"""ffprobe wrappers returning structured stream/format info."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.media.ffmpeg import run_ffprobe


def probe(path: Path) -> dict:
    out = run_ffprobe(
        ["-print_format", "json", "-show_format", "-show_streams", str(path)]
    )
    return json.loads(out)


def _to_float(v) -> float | None:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None  # missing, "N/A", or non-positive -> unknown


def _resolve_duration(info: dict) -> float:
    """format.duration -> longest stream.duration -> 0.0 (unknown). Never raises: some containers
    (raw streams, fragmented mp4, webm without a global duration) omit format.duration or report
    'N/A', which used to KeyError/ValueError and crash the run."""
    d = _to_float((info.get("format") or {}).get("duration"))
    if d is not None:
        return d
    best = 0.0
    for s in info.get("streams") or []:
        sd = _to_float(s.get("duration"))
        if sd:
            best = max(best, sd)
    return best


def duration_s(path: Path) -> float:
    """Resolved source duration. The core pipeline genuinely needs it, so an unresolvable duration
    fails loud with an actionable message rather than returning a silent 0 that breaks compile."""
    d = _resolve_duration(probe(path))
    if d <= 0:
        from eddy.media.ffmpeg import FfmpegError

        raise FfmpegError(f"could not determine duration of {path} — corrupt or unsupported container?")
    return d


def stream_summary(path: Path) -> dict:
    info = probe(path)
    streams = info.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return {
        "duration_s": _resolve_duration(info),  # 0.0 if unknown; QA gates on > 1, never crashes here
        "video": None
        if v is None
        else {
            "codec": v.get("codec_name"),
            "width": v.get("width"),
            "height": v.get("height"),
            "fps": eval_fps(v.get("avg_frame_rate", "0/1")),
        },
        "audio": None
        if a is None
        else {
            "codec": a.get("codec_name"),
            "sample_rate": int(_to_float(a.get("sample_rate")) or 0),
            "channels": a.get("channels"),
        },
    }


def eval_fps(rate: str | None) -> float:
    # ffprobe can emit avg_frame_rate: null (-> None, since .get default only fills MISSING keys),
    # which used to crash on None.split(). Coerce + catch AttributeError.
    try:
        num, den = str(rate or "0/1").split("/")
        return round(int(num) / int(den), 3) if int(den) else 0.0
    except (ValueError, ZeroDivisionError, AttributeError):
        return 0.0
