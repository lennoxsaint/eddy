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


def render(src: Path, segments: list[list[float]], out: Path, xfade: float) -> None:
    """Frame-accurate concat via trim/atrim filter_complex, with a micro audio crossfade at joins."""
    parts_v, parts_a, labels = [], [], []
    for i, (s, e) in enumerate(segments):
        parts_v.append(
            f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        parts_a.append(
            f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={xfade},areverse,afade=t=in:st=0:d={xfade},areverse[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    concat = "".join(labels) + f"concat=n={len(segments)}:v=1:a=1[v][a]"
    fc = ";".join(parts_v + parts_a + [concat])

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2000:], file=sys.stderr)
        raise RuntimeError("ffmpeg splice failed")


def main() -> int:
    ap = argparse.ArgumentParser(description="Execute a cut list into an edited video.")
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--words", required=True)
    ap.add_argument("--cutlist", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--gap-threshold", type=float, default=None)
    ap.add_argument("--gap-target", type=float, default=None)
    ap.add_argument("--xfade", type=float, default=0.06)
    args = ap.parse_args()

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
    render(Path(args.inp), segments, out, args.xfade)

    kept = round(sum(e - s for s, e in segments), 2)
    (out.parent / (out.stem + ".segments.json")).write_text(
        json.dumps({"segments": segments, "kept_seconds": kept,
                    "gap_threshold": threshold, "gap_target": target}, indent=1))
    print(json.dumps({"event": "spliced", "segments": len(segments), "kept_seconds": kept,
                      "out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
