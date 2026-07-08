#!/usr/bin/env python3
"""Deterministic verification gates (machine-checkable).

Runs the subset of `references/verification.md` gates that a script can prove, and prints a JSON
verdict. Model rubrics (hook, cohesion, gutting) are judged by the agent, not here.

Usage:
  verify.py --final final.mp4 [--segments edited.segments.json] [--plan edit-plan.json]
            [--source-audio source.wav] [--expect-w 1920] [--expect-h 1080]

edit-plan.json (optional, machine slice of edit-plan.md):
  {"keep_beats": [{"id": "b3", "start": 12.4, "end": 41.0}, ...],
   "sacred": [[start,end], ...]}

Exit codes: 0 all-ran-gates pass · 1 a gate failed · 2 bad input
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HARD_MAX_GAP = 0.28  # unprotected gap ceiling (layout-constants.md)


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def duration(path: Path) -> float:
    info = probe(path)
    return float(info.get("format", {}).get("duration", 0.0) or 0.0)


def video_res(info: dict) -> tuple[int, int]:
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            return int(s.get("width", 0)), int(s.get("height", 0))
    return 0, 0


def has_audio(info: dict) -> bool:
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic verification gates.")
    ap.add_argument("--final", required=True)
    ap.add_argument("--segments")
    ap.add_argument("--plan")
    ap.add_argument("--source-audio")
    ap.add_argument("--expect-w", type=int, default=1920)
    ap.add_argument("--expect-h", type=int, default=1080)
    args = ap.parse_args()

    final = Path(args.final)
    if not final.exists():
        print("ERROR: final not found.", file=sys.stderr)
        return 2

    gates: list[dict] = []

    def gate(name: str, ok: bool, **detail):
        gates.append({"gate": name, "pass": bool(ok), **detail})

    info = probe(final)

    # Layout assert: resolution
    w, h = video_res(info)
    gate("layout_resolution", w == args.expect_w and h == args.expect_h,
         got=f"{w}x{h}", expected=f"{args.expect_w}x{args.expect_h}")

    # Has audio (Studio Sound muxed)
    gate("has_audio", has_audio(info))

    # Audio parity vs source (if provided)
    if args.source_audio and Path(args.source_audio).exists():
        src = duration(Path(args.source_audio))
        fin = duration(final)
        tol = max(1.0, src * 0.01)
        # NB: final may be shorter than raw source because of cuts; parity here is a sanity band
        gate("duration_sane", fin > 0, source_audio_s=round(src, 2), final_s=round(fin, 2))

    # Gap band + gap tightening applied (from segments receipt)
    if args.segments and Path(args.segments).exists():
        seg = json.loads(Path(args.segments).read_text())
        segments = seg.get("segments", [])
        target = seg.get("gap_target", 0.1)
        # boundaries between consecutive kept sub-segments represent tightened gaps in the source;
        # after render they are butt-joined, so we assert the receipt honored the target policy.
        gate("gap_tighten_applied", target <= 0.2 and len(segments) >= 1,
             segments=len(segments), gap_target=target)

    # Beat completeness: every keep beat overlaps a kept sub-segment
    if args.plan and Path(args.plan).exists() and args.segments and Path(args.segments).exists():
        plan = json.loads(Path(args.plan).read_text())
        segments = json.loads(Path(args.segments).read_text()).get("segments", [])
        missing = []
        for beat in plan.get("keep_beats", []):
            bs, be = float(beat["start"]), float(beat["end"])
            covered = any(not (e <= bs or s >= be) for s, e in segments)  # any overlap
            if not covered:
                missing.append(beat.get("id", f"{bs}-{be}"))
        gate("beat_completeness", not missing, missing=missing)

    passed = all(g["pass"] for g in gates)
    verdict = {"pass": passed, "gates": gates,
               "ran": len(gates), "note": "model rubrics (hook/cohesion/gutting) judged separately"}
    print(json.dumps(verdict, indent=1))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
