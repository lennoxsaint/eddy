#!/usr/bin/env python3
"""Cut-list executor — turns the model's decisions into an edited video (deterministic).

Consumes the beat-map "Cut list" (kept source spans) + word timings, then:
  1. tightens inter-word gaps > threshold down to target (SOP step 4), sacred spans exempt,
  2. concatenates the resulting sub-segments frame-accurately with a micro audio crossfade.

The MODEL decides what to keep (retakes out, tangents out, clarity) and writes the cut list;
this script only executes it. Never regenerates or overdubs — it only removes real recorded time.

Usage:
  splice.py --in source.mp4 --words transcript.json --cutlist cutlist.json --out edited.mp4
            [--gap-threshold 0.2] [--gap-target 0.1] [--xfade 0.06]

cutlist.json:
  {"keep": [[start,end], ...],            # source seconds, in order
   "sacred": [[start,end], ...],          # spans exempt from gap tightening
   "gap_tighten": {"threshold": 0.2, "target": 0.1}}   # optional; CLI flags override

Emits `edited.segments.json` next to --out: the exact source sub-segments used (a receipt).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# V1 cut-safety handles (seconds) — layout-constants.md
MIN_BOUNDARY_HANDLE = 0.10


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def in_any(t: float, spans: list[list[float]]) -> bool:
    return any(s <= t <= e for s, e in spans)


def compute_segments(keep: list[list[float]], words: list[dict], sacred: list[list[float]],
                     threshold: float, target: float) -> list[list[float]]:
    """Within each kept span, cap inter-word gaps > threshold to `target` (unless sacred).

    Returns an ordered list of source sub-segments [start,end] to concatenate.
    """
    segments: list[list[float]] = []
    for span_start, span_end in keep:
        # words fully inside this kept span
        inside = [w for w in words if w["start"] >= span_start - 1e-6 and w["end"] <= span_end + 1e-6]
        if not inside:
            segments.append([span_start, span_end])
            continue
        cursor = span_start
        seg_start = span_start
        for i, w in enumerate(inside):
            if i == 0:
                continue
            gap_start = inside[i - 1]["end"]
            gap_end = w["start"]
            gap = gap_end - gap_start
            # sacred gaps (deliberate pauses / breath) are never tightened
            mid = (gap_start + gap_end) / 2.0
            if gap > threshold + 1e-6 and not in_any(mid, sacred):
                # close the current sub-segment at gap_start + target, then jump to gap_end
                keep_until = gap_start + target
                segments.append([seg_start, keep_until])
                seg_start = gap_end
            cursor = w["end"]
        segments.append([seg_start, span_end])
    # drop zero/negative-length segments
    return [[round(s, 3), round(e, 3)] for s, e in segments if e - s > 0.02]


def render(src: Path, segments: list[list[float]], out: Path, xfade: float,
           scale: tuple[int, int] | None = None, fps: int = 30) -> None:
    """Single-pass select/aselect: keep only frames inside the kept segments, re-stamp timestamps
    to remove the gaps. One decode + a per-frame keep-test — scales to hundreds of segments, where a
    trim+concat filter_complex would split every decoded frame N ways and crawl (O(frames × N)).

    Normalizes to constant `fps` first, so a VFR / odd-fps source (e.g. a 29.97/29.67 screen track)
    comes out CFR and stays frame-synced with a co-spliced camera track cut from the same list.

    `scale` (W,H) optionally downscales during the cut (aspect-preserving, padded) — use it to cut a
    4K screen track straight to 1080p so the encode is 1080p not 4K (machine-safety: no heavy 4K
    encode; the composite scales the screen to 1080p anyway). Hard cuts land on word-gap silence, so
    no audio crossfade is needed (`xfade` kept for signature compatibility, unused here).
    """
    # Render VIDEO and AUDIO in SEPARATE passes, then mux. Doing both in one filter_complex makes the
    # muxer buffer video while the N-input audio concat catches up — with hundreds of segments that
    # starves into a stall. Separate passes have no cross-stream sync, so each runs clean and fast.
    out.parent.mkdir(parents=True, exist_ok=True)
    vtmp = out.with_suffix(".vonly.mp4")
    atmp = out.with_suffix(".aonly.m4a")

    def ff(cmd: list[str], what: str) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr[-2000:], file=sys.stderr)
            raise RuntimeError(f"ffmpeg splice {what} failed")

    # VIDEO: one decode, per-frame keep-test (select), re-stamp to drop gaps. fps normalizes CFR.
    expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in segments)
    if scale:
        sw, sh = scale
        vscale = (f",scale={sw}:{sh}:force_original_aspect_ratio=decrease,"
                  f"pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    else:
        vscale = ""
    ff(["ffmpeg", "-y", "-i", str(src), "-map", "0:v:0", "-an",
        "-vf", f"fps={fps},select='{expr}',setpts=N/FRAME_RATE/TB{vscale}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-movflags", "+faststart", str(vtmp)], "video")

    # AUDIO: atrim each kept span + concat (aselect doesn't drop frames in this ffmpeg build). Audio
    # only — no video decode, no cross-stream sync — so hundreds of segments stay cheap.
    aparts = [f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]"
              for i, (s, e) in enumerate(segments)]
    alabels = "".join(f"[a{i}]" for i in range(len(segments)))
    afc = ";".join(aparts + [f"{alabels}concat=n={len(segments)}:v=0:a=1[a]"])
    ff(["ffmpeg", "-y", "-i", str(src), "-vn", "-filter_complex", afc, "-map", "[a]",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(atmp)], "audio")

    # MUX (stream copy) — no sync problem, just interleave the two finished streams.
    ff(["ffmpeg", "-y", "-i", str(vtmp), "-i", str(atmp), "-map", "0:v:0", "-map", "1:a:0",
        "-c", "copy", "-movflags", "+faststart", str(out)], "mux")
    for t in (vtmp, atmp):
        try:
            t.unlink()
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Execute a cut list into an edited video.")
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--words", required=True)
    ap.add_argument("--cutlist", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--gap-threshold", type=float, default=None)
    ap.add_argument("--gap-target", type=float, default=None)
    ap.add_argument("--xfade", type=float, default=0.06)
    ap.add_argument("--scale", default=None,
                    help="WxH — downscale each cut segment (e.g. 1920x1080 for a 4K screen track)")
    args = ap.parse_args()

    scale = None
    if args.scale:
        try:
            sw, sh = (int(x) for x in args.scale.lower().split("x"))
            scale = (sw, sh)
        except ValueError:
            print("ERROR: --scale must be WxH, e.g. 1920x1080.", file=sys.stderr)
            return 2

    words = load(args.words).get("words", [])
    cut = load(args.cutlist)
    keep = cut.get("keep", [])
    sacred = cut.get("sacred", [])
    gt = cut.get("gap_tighten", {})
    threshold = args.gap_threshold if args.gap_threshold is not None else gt.get("threshold", 0.2)
    target = args.gap_target if args.gap_target is not None else gt.get("target", 0.1)

    if not keep:
        print("ERROR: cut list has no 'keep' spans.", file=sys.stderr)
        return 2

    segments = compute_segments(keep, words, sacred, threshold, target)
    if not segments:
        print("ERROR: computed zero segments — check keep spans vs word timings.", file=sys.stderr)
        return 3

    out = Path(args.out)
    render(Path(args.inp), segments, out, args.xfade, scale)

    kept = round(sum(e - s for s, e in segments), 2)
    (out.parent / (out.stem + ".segments.json")).write_text(
        json.dumps({"segments": segments, "kept_seconds": kept,
                    "gap_threshold": threshold, "gap_target": target}, indent=1))
    print(json.dumps({"event": "spliced", "segments": len(segments), "kept_seconds": kept,
                      "out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
