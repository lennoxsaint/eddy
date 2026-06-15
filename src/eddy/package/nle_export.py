"""Editor-native timeline export.

Agencies finish in an NLE, not in Eddy's take-it-or-leave-it render. A CMX3600 EDL is the universal
text interchange (Premiere, Resolve, FCP, Avid all import it): each kept EDL range becomes a cut
event mapping a source in/out to a record (timeline) in/out. Retimed (speed != 1.0) events get the
correct *record* duration — source_len / speed — so the timeline matches the rendered video.mp4,
plus a CMX3600 M2 motion-memory line documenting the playback rate (NLEs that honor M2 conform the
retime exactly; the record cut points align either way).
"""

from __future__ import annotations

from pathlib import Path

from eddy.edit.schema import Edl


def _tc(seconds: float, fps: int) -> str:
    total_frames = int(round(max(0.0, seconds) * fps))
    f = total_frames % fps
    s = (total_frames // fps) % 60
    m = (total_frames // (fps * 60)) % 60
    h = total_frames // (fps * 3600)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def build_cmx3600(edl: Edl, fps: int = 30, title: str = "EDDY EDIT", reel: str = "AX") -> str:
    src_name = Path(next(iter(edl.sources.values()), "source.mp4")).name
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    rec = 0.0
    for i, r in enumerate(edl.ranges, 1):
        speed = r.speed if r.speed and r.speed > 0 else 1.0
        src_len = max(0.0, r.end - r.start)
        rec_len = src_len / speed  # record timeline must match the rendered (sped) video, not source len
        rec_in, rec_out = rec, rec + rec_len
        lines.append(
            f"{i:03d}  {reel:<7} AA/V  C        "
            f"{_tc(r.start, fps)} {_tc(r.end, fps)} {_tc(rec_in, fps)} {_tc(rec_out, fps)}"
        )
        lines.append(f"* FROM CLIP NAME: {src_name}")
        if abs(speed - 1.0) > 1e-6:
            # CMX3600 motion-memory: projected playback rate = base fps * speed multiplier
            lines.append(f"M2   {reel:<7} {fps * speed:>6.1f}        {_tc(r.start, fps)}")
        rec = rec_out
    return "\n".join(lines) + "\n"


def write_edl(edl: Edl, out_dir: Path, fps: int = 30, title: str = "EDDY EDIT") -> Path:
    out = Path(out_dir) / "timeline.edl"
    out.write_text(build_cmx3600(edl, fps=fps, title=title))
    return out
