"""Sidecar subtitle files (.srt + .vtt) of the final cut, on the OUTPUT timeline.

The shorts carry burned-in karaoke captions, but the long video shipped no subtitle track — an
accessibility gap (deaf/HoH viewers, YouTube's own captions) and an SEO miss. These are generated
from the cut transcript's output-timeline phrases and dropped into the launch kit.
"""

from __future__ import annotations

from pathlib import Path


def _ts(seconds: float, sep: str) -> str:
    # derive everything from one rounded-ms integer so the carry cascades through s/m/h correctly
    # (the old per-field math produced ':60' at minute/hour boundaries — invalid SRT/VTT).
    total_ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _cues(phrases: list[dict]) -> list[dict]:
    out = []
    for p in phrases:
        text = (p.get("text") or "").strip()
        start = p.get("out_start")
        end = p.get("out_end")
        if not text or start is None or end is None or end <= start:
            continue
        out.append({"start": float(start), "end": float(end), "text": text})
    return out


def build_srt(phrases: list[dict]) -> str:
    lines = []
    for i, c in enumerate(_cues(phrases), 1):
        lines.append(str(i))
        lines.append(f"{_ts(c['start'], ',')} --> {_ts(c['end'], ',')}")
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines)


def build_vtt(phrases: list[dict]) -> str:
    lines = ["WEBVTT", ""]
    for c in _cues(phrases):
        lines.append(f"{_ts(c['start'], '.')} --> {_ts(c['end'], '.')}")
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines)


def write_subtitles(phrases: list[dict], out_dir: Path, stem: str = "subtitles") -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    srt = out_dir / f"{stem}.srt"
    vtt = out_dir / f"{stem}.vtt"
    srt.write_text(build_srt(phrases))
    vtt.write_text(build_vtt(phrases))
    return {"srt": srt, "vtt": vtt, "cues": len(_cues(phrases))}
