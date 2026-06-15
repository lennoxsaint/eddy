"""Editor-native timeline export.

Agencies finish in an NLE, not in Eddy's take-it-or-leave-it render. A CMX3600 EDL is the universal
text interchange (Premiere, Resolve, FCP, Avid all import it): each kept EDL range becomes a cut
event mapping a source in/out to a record (timeline) in/out. Speed ramps aren't representable in a
basic EDL, so it's exported as a straight 1.0x cut list (the default path; speed-ramp is opt-in).
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
        length = max(0.0, r.end - r.start)
        rec_in, rec_out = rec, rec + length
        lines.append(
            f"{i:03d}  {reel:<7} AA/V  C        "
            f"{_tc(r.start, fps)} {_tc(r.end, fps)} {_tc(rec_in, fps)} {_tc(rec_out, fps)}"
        )
        lines.append(f"* FROM CLIP NAME: {src_name}")
        rec = rec_out
    return "\n".join(lines) + "\n"


def write_edl(edl: Edl, out_dir: Path, fps: int = 30, title: str = "EDDY EDIT") -> Path:
    out = Path(out_dir) / "timeline.edl"
    out.write_text(build_cmx3600(edl, fps=fps, title=title))
    return out
