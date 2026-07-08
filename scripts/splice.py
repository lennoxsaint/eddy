#!/usr/bin/env python3
"""Cut-list executor — turns the model's decisions into an edited video (deterministic).

Consumes the beat-map "Cut list" (kept source spans) + word timings, then:
  1. removes dead air: any silence > threshold (from ffmpeg `silencedetect` AND inter-word gaps)
     is capped to `target`, sacred spans exempt. silencedetect is the ground truth — it catches
     silence with NO transcribed words (long dead air, an untranscribed false-start) that the old
     word-only logic passed straight through.
  2. concatenates the resulting sub-segments frame-accurately with a short, length-preserving
     de-click fade at every join (no click/pop at cuts).

The MODEL decides what to keep (retakes out, tangents out, clarity) and writes the cut list;
this script only executes it. Never regenerates or overdubs — it only removes real recorded time.

Usage:
  splice.py --in source.mp4 --words transcript.json --cutlist cutlist.json --out edited.mp4
            [--gap-threshold 0.2] [--gap-target 0.1] [--xfade 0.012] [--silence-db -30]
            [--segments prior.segments.json]   # reuse EXACT segments (co-splice a screen track)

cutlist.json:
  {"keep": [[start,end], ...],            # source seconds, in order
   "sacred": [[start,end], ...],          # spans exempt from gap tightening
   "gap_tighten": {"threshold": 0.2, "target": 0.1}}   # optional; CLI flags override

To keep a screen track frame-synced with the camera: splice the camera first (it has audio, so it
owns the silence-driven cut), then splice the screen with `--segments <camera>.segments.json` so it
reuses the identical sub-segments instead of recomputing (the screen has no audio to silencedetect).

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


def detect_silences(src: Path, noise_db: float, min_dur: float) -> list[list[float]]:
    """Ground-truth dead-air spans via ffmpeg silencedetect (audio energy, transcript-independent).

    Returns [[start,end], ...] for every silence longer than `min_dur`. This is what catches the
    long wordless gaps the word-only tightener missed. Audio-only decode — cheap even on 75 min.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(src),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_dur:.3f}", "-f", "null", "-"],
        capture_output=True, text=True)
    spans: list[list[float]] = []
    pending: float | None = None
    for line in proc.stderr.splitlines():
        if "silence_start:" in line:
            try:
                pending = float(line.split("silence_start:")[1].strip())
            except ValueError:
                pending = None
        elif "silence_end:" in line and pending is not None:
            try:
                end = float(line.split("silence_end:")[1].split("|")[0].strip())
                spans.append([pending, end])
            except ValueError:
                pass
            pending = None
    return spans


def _merge(intervals: list[list[float]]) -> list[list[float]]:
    intervals = sorted(intervals)
    merged: list[list[float]] = []
    for a, b in intervals:
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def span_gaps(span_start: float, span_end: float, inside: list[dict],
              silences: list[list[float]], sacred: list[list[float]],
              threshold: float) -> list[list[float]]:
    """Every stretch inside [span_start,span_end] that should be tightened: word-gaps AND detected
    silences (incl. leading/trailing), > threshold, whose midpoint is not sacred. Merged + sorted."""
    gaps: list[list[float]] = []
    if inside:
        if inside[0]["start"] - span_start > threshold:
            gaps.append([span_start, inside[0]["start"]])
        for i in range(1, len(inside)):
            g0, g1 = inside[i - 1]["end"], inside[i]["start"]
            if g1 - g0 > threshold:
                gaps.append([g0, g1])
        if span_end - inside[-1]["end"] > threshold:
            gaps.append([inside[-1]["end"], span_end])
    for ss, se in silences:
        a, b = max(ss, span_start), min(se, span_end)
        if b - a > threshold:
            gaps.append([a, b])
    gaps = [g for g in gaps if not in_any((g[0] + g[1]) / 2.0, sacred)]
    return _merge(gaps)


def compute_segments(keep: list[list[float]], words: list[dict], sacred: list[list[float]],
                     threshold: float, target: float,
                     silences: list[list[float]]) -> list[list[float]]:
    """Within each kept span, cap every dead-air stretch > threshold to `target` (unless sacred).

    Dead air = word-gaps OR silencedetect spans (so a span with no words is still tightened).
    Returns an ordered list of source sub-segments [start,end] to concatenate.
    """
    segments: list[list[float]] = []
    for span_start, span_end in keep:
        inside = [w for w in words if w["start"] >= span_start - 1e-6 and w["end"] <= span_end + 1e-6]
        seg_start = span_start
        for g0, g1 in span_gaps(span_start, span_end, inside, silences, sacred, threshold):
            keep_until = g0 + target
            if keep_until > seg_start + 1e-6:
                segments.append([seg_start, keep_until])
            seg_start = g1
        if span_end > seg_start + 1e-6:
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
    encode; the composite scales the screen to 1080p anyway).

    De-click: not every cut lands on true silence, so a raw butt-join clicks. `xfade` (seconds, ~12ms)
    is applied as a short afade in+out at each segment's own edges — length-preserving (the segment
    keeps its exact duration, so the audio stays frame-synced with the separately-select'd video; a
    real acrossfade would shorten audio and desync it). Inaudible on gap cuts, kills the click on
    mid-speech cuts.
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

    # AUDIO: atrim each kept span + a short in/out fade (de-click) + concat (aselect doesn't drop
    # frames in this ffmpeg build). Audio only — no video decode, no cross-stream sync — so hundreds
    # of segments stay cheap. The fade is capped at dur/3 so very short segments don't over-fade.
    aparts = []
    for i, (s, e) in enumerate(segments):
        dur = e - s
        fd = max(0.001, min(xfade, dur / 3.0))
        aparts.append(
            f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fd:.4f},afade=t=out:st={max(0.0, dur - fd):.4f}:d={fd:.4f}[a{i}]")
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
    ap.add_argument("--xfade", type=float, default=0.012,
                    help="de-click fade at each join, seconds (length-preserving)")
    ap.add_argument("--silence-db", type=float, default=-30.0,
                    help="silencedetect noise floor in dB (dead-air detection)")
    ap.add_argument("--segments", default=None,
                    help="reuse the exact segments from a prior .segments.json (co-splice a screen track)")
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

    cut = load(args.cutlist)
    gt = cut.get("gap_tighten", {})
    threshold = args.gap_threshold if args.gap_threshold is not None else gt.get("threshold", 0.2)
    target = args.gap_target if args.gap_target is not None else gt.get("target", 0.1)

    if args.segments:
        # co-splice mode: reuse the EXACT sub-segments a prior run computed (keeps a screen track
        # frame-synced with the camera that owns the silence-driven cut).
        segments = load(args.segments).get("segments", [])
        if not segments:
            print("ERROR: --segments file has no 'segments'.", file=sys.stderr)
            return 2
    else:
        words = load(args.words).get("words", [])
        keep = cut.get("keep", [])
        sacred = cut.get("sacred", [])
        if not keep:
            print("ERROR: cut list has no 'keep' spans.", file=sys.stderr)
            return 2
        silences = detect_silences(Path(args.inp), args.silence_db, threshold)
        segments = compute_segments(keep, words, sacred, threshold, target, silences)
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
