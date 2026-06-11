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


def duration_s(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def stream_summary(path: Path) -> dict:
    info = probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    return {
        "duration_s": float(info["format"]["duration"]),
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
            "sample_rate": int(a.get("sample_rate", 0)),
            "channels": a.get("channels"),
        },
    }


def eval_fps(rate: str) -> float:
    try:
        num, den = rate.split("/")
        return round(int(num) / int(den), 3) if int(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0
