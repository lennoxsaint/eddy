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
            [--gap-threshold 0.2] [--gap-target 0.1] [--xfade 0.012] [--silence-db -27]
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
import re
import subprocess
import sys
from pathlib import Path

# V1 cut-safety handles (seconds) — layout-constants.md
MIN_BOUNDARY_HANDLE = 0.10
PROTECTED_PAUSE_CEILING = 0.8
WORD_ONSET_HANDLE = 0.06
MAX_WORD_PROTECTION = 1.0
SEEK_PREROLL = 0.1


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
        ["ffmpeg", "-hide_banner", "-i", str(src), "-vn",
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


def _subtract_intervals(
    intervals: list[list[float]],
    protected: list[list[float]],
) -> list[list[float]]:
    result = intervals
    for protected_start, protected_end in protected:
        updated: list[list[float]] = []
        for start, end in result:
            if protected_end <= start or protected_start >= end:
                updated.append([start, end])
                continue
            if protected_start > start:
                updated.append([start, protected_start])
            if protected_end < end:
                updated.append([protected_end, end])
        result = updated
    return result


def _word_protection(word: dict) -> list[float]:
    start, end = float(word["start"]), float(word["end"])
    return [start, min(end, start + MAX_WORD_PROTECTION)]


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def detect_retakes(words: list[dict], ngram: int = 4, window_s: float = 3.0,
                   sacred: list[list[float]] | None = None) -> list[dict]:
    """Find IMMEDIATE stutters / false-starts and return the short spans to DROP.

    When the same `ngram` word-sequence recurs within `window_s`, drop [earlier_start, later_start)
    (keep the LATER take — last-take bias). CRITICAL: the window MUST stay small (~4s). A genuine
    false-start restarts within a couple of seconds, so the dropped span is short. A LARGE window is
    wrong — common 4-grams recur naturally in speech seconds apart ("your ai coding model", "you
    dont have to"), and dropping the whole inter-occurrence span would butcher legit content (a 20s
    window dropped 124 legit >5s spans in testing). Wide-gap retakes are handled by explicit --drop,
    not this scan; verify.py's blocking gate catches any survivor. A repeat whose midpoint is sacred
    is never dropped. Returns [{"span":[a,b], "phrase": "..."}]; overlaps merged by the caller.
    """
    sacred = sacred or []
    toks = [(_norm(w.get("word", "")), w) for w in words]
    toks = [(t, w) for t, w in toks if t]
    drops: list[dict] = []
    seen: dict[tuple, float] = {}
    for i in range(len(toks) - ngram + 1):
        key = tuple(t for t, _ in toks[i:i + ngram])
        start = toks[i][1]["start"]
        prev = seen.get(key)
        if prev is not None and 0 < start - prev <= window_s:
            if not in_any((prev + start) / 2.0, sacred):
                drops.append({"span": [round(prev, 3), round(start, 3)], "phrase": " ".join(key)})
        seen[key] = start
    return drops


def subtract_spans(keep: list[list[float]], drops: list[list[float]]) -> list[list[float]]:
    """Remove every drop span from the keep spans, splitting a keep span around an interior drop.

    A drop outside all keep spans is a no-op. Used to excise retakes / explicit drops from the
    coarse content selection BEFORE gap-tightening, so they never reach the cut.
    """
    drops = _merge([list(d) for d in drops])
    result: list[list[float]] = []
    for s, e in keep:
        cur = [[s, e]]
        for da, db in drops:
            nxt: list[list[float]] = []
            for cs, ce in cur:
                if db <= cs or da >= ce:          # no overlap
                    nxt.append([cs, ce])
                    continue
                if da > cs:
                    nxt.append([cs, da])          # piece before the drop
                if db < ce:
                    nxt.append([db, ce])          # piece after the drop
            cur = nxt
        result.extend([c for c in cur if c[1] - c[0] > 0.02])
    return result


def span_gaps(span_start: float, span_end: float, inside: list[dict],
              silences: list[list[float]], sacred: list[list[float]],
              threshold: float) -> list[list[float]]:
    """Every stretch inside [span_start,span_end] that should be tightened: word-gaps AND detected
    silences (incl. leading/trailing), > threshold. Protection may retain a short pause, but it can
    never hide silence above the protected-pause ceiling. Merged + sorted."""
    transcript_gaps: list[list[float]] = []
    if inside:
        # Two retained keep edges meet in the delivered timeline. Cap each edge independently so
        # individually sub-threshold pauses cannot add up to a slow join after concatenation.
        boundary_threshold = min(threshold, MIN_BOUNDARY_HANDLE)
        if inside[0]["start"] - span_start > boundary_threshold:
            transcript_gaps.append([span_start, inside[0]["start"]])
        for i in range(1, len(inside)):
            g0, g1 = inside[i - 1]["end"], inside[i]["start"]
            if g1 - g0 > threshold:
                transcript_gaps.append([g0, g1])
        if span_end - inside[-1]["end"] > boundary_threshold:
            transcript_gaps.append([inside[-1]["end"], span_end])
    transcript_gaps = _subtract_intervals(
        _merge(transcript_gaps),
        [_word_protection(word) for word in inside],
    )
    audio_gaps: list[list[float]] = []
    for ss, se in silences:
        a, b = max(ss, span_start), min(se, span_end)
        if b - a > threshold:
            audio_gaps.append([a, b])
    # Measured silence is audio truth and must not be weakened by malformed Whisper durations.
    # Transcript word protection applies only to transcript-inferred gaps; the configured handles
    # below preserve word onsets at measured-silence boundaries.
    gaps = _merge([*transcript_gaps, *audio_gaps])
    gaps = [
        gap
        for gap in gaps
        if not (
            in_any((gap[0] + gap[1]) / 2.0, sacred)
            and gap[1] - gap[0] <= PROTECTED_PAUSE_CEILING
        )
    ]
    return _merge(gaps)


def compute_segments(keep: list[list[float]], words: list[dict], sacred: list[list[float]],
                     threshold: float, target: float,
                     silences: list[list[float]], max_gap: float = 0.28) -> list[list[float]]:
    """Within each kept span, cap every dead-air stretch > threshold to `target` (unless sacred).

    Dead air = word-gaps OR silencedetect spans (so a span with no words is still tightened).
    HARD max-gap: the tightening trigger is min(threshold, max_gap), so no internal gap can ever
    exceed `max_gap` regardless of the configured threshold — the belt-and-suspenders guarantee that
    a long wordless stretch (that a high threshold or a missed silencedetect could let slip) is still
    collapsed. Returns an ordered list of source sub-segments [start,end] to concatenate.
    """
    eff_threshold = min(threshold, max_gap)
    keep_len = min(target, max_gap)
    onset_handle = min(WORD_ONSET_HANDLE, keep_len)
    trailing_handle = max(0.0, keep_len - onset_handle)
    segments: list[list[float]] = []
    for span_start, span_end in keep:
        inside = [w for w in words if w["start"] >= span_start - 1e-6 and w["end"] <= span_end + 1e-6]
        if inside:
            first_start = float(inside[0]["start"])
            last_end = float(inside[-1]["end"])
            leading_midpoint = (span_start + first_start) / 2.0
            trailing_midpoint = (last_end + span_end) / 2.0
            if first_start - span_start > onset_handle and not in_any(leading_midpoint, sacred):
                span_start = first_start - onset_handle
            if span_end - last_end > trailing_handle and not in_any(trailing_midpoint, sacred):
                span_end = last_end + trailing_handle
        seg_start = span_start
        for g0, g1 in span_gaps(span_start, span_end, inside, silences, sacred, eff_threshold):
            touches_start = g0 <= span_start + 1e-6
            touches_end = g1 >= span_end - 1e-6
            keep_until = g0 if touches_start else g0 + trailing_handle
            if keep_until > seg_start + 1e-6:
                segments.append([seg_start, keep_until])
            seg_start = span_end if touches_end else max(keep_until, g1 - onset_handle)
        if span_end > seg_start + 1e-6:
            segments.append([seg_start, span_end])
    # drop zero/negative-length segments
    return [[round(s, 3), round(e, 3)] for s, e in segments if e - s > 0.02]


def build_audio_filter(segments: list[list[float]], xfade: float) -> tuple[str, str]:
    """Build an O(frames + segments) audio splice graph for this FFmpeg build.

    ``aselect`` is intentionally not used: the macOS FFmpeg build used for Eddy routes frames with
    a zero/NaN selection result instead of dropping them. ``asegment`` decodes once and sends each
    audio frame to exactly one interval. Odd outputs are the requested keep spans; even outputs are
    discarded. This avoids the old N-way ``atrim`` fan-out that made a 329-cut edit appear stalled.
    """
    normalized = _merge([list(segment) for segment in segments])
    if not normalized:
        raise ValueError("audio splice requires at least one segment")
    boundaries = [point for segment in normalized for point in segment]
    if any(end <= start for start, end in normalized):
        raise ValueError("audio splice segments must have positive duration")

    output_count = len(boundaries) + 1
    outputs = "".join(f"[as{i}]" for i in range(output_count))
    timestamps = "|".join(f"{point:.3f}" for point in boundaries)
    filters = [f"[0:a]asegment=timestamps={timestamps}{outputs}"]
    keep_labels: list[str] = []
    for output_index in range(output_count):
        if output_index % 2 == 0:
            filters.append(f"[as{output_index}]anullsink")
            continue
        segment_index = output_index // 2
        start, end = normalized[segment_index]
        duration = end - start
        fade_duration = max(0.001, min(xfade, duration / 3.0))
        keep_label = f"ak{segment_index}"
        keep_labels.append(f"[{keep_label}]")
        filters.append(
            f"[as{output_index}]asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_duration:.4f},"
            f"afade=t=out:st={max(0.0, duration - fade_duration):.4f}:d={fade_duration:.4f}"
            f"[{keep_label}]"
        )

    if len(keep_labels) == 1:
        filters.append(
            f"{keep_labels[0]}adeclick=w=55:o=75:a=2:t=2:b=2:m=s[aout]"
        )
    else:
        filters.append(
            f"{''.join(keep_labels)}concat=n={len(keep_labels)}:v=0:a=1,"
            "adeclick=w=55:o=75:a=2:t=2:b=2:m=s[aout]"
        )
    return ";".join(filters), "[aout]"


def localize_segments(
    segments: list[list[float]],
    *,
    seek_preroll: float = SEEK_PREROLL,
) -> tuple[float, float, list[list[float]]]:
    """Translate source-time segments into a bounded, accurately-seeked decode window."""
    normalized = _merge([list(segment) for segment in segments])
    if not normalized:
        raise ValueError("splice requires at least one segment")
    seek_start = max(0.0, normalized[0][0] - seek_preroll)
    seek_end = normalized[-1][1] + seek_preroll
    localized = [
        [round(start - seek_start, 6), round(end - seek_start, 6)]
        for start, end in normalized
    ]
    return seek_start, seek_end - seek_start, localized


def build_video_timeline(segments: list[list[float]]) -> tuple[str, str]:
    """Return a frame selector and gapless PTS expression that preserve source durations."""
    def balanced_sum(terms: list[str]) -> str:
        if not terms:
            return "0"
        while len(terms) > 1:
            paired: list[str] = []
            for index in range(0, len(terms), 2):
                if index + 1 < len(terms):
                    paired.append(f"({terms[index]}+{terms[index + 1]})")
                else:
                    paired.append(terms[index])
            terms = paired
        return terms[0]

    selectors: list[str] = []
    for start, end in segments:
        condition = f"gte(T,{start:.6f})*lt(T,{end:.6f})"
        selectors.append(condition.replace("T", "t"))
    removed_terms = [f"{segments[0][0]:.6f}"]
    for previous, current in zip(segments, segments[1:], strict=False):
        gap = current[0] - previous[1]
        if gap > 1e-9:
            removed_terms.append(f"{gap:.6f}*gte(T,{current[0]:.6f})")
    timeline = f"(T-({balanced_sum(removed_terms)}))/TB"
    return balanced_sum(selectors), timeline


def render(src: Path, segments: list[list[float]], out: Path, xfade: float,
           scale: tuple[int, int] | None = None, fps: int = 30, no_audio: bool = False) -> None:
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
    seek_start, seek_duration, local_segments = localize_segments(segments)
    input_args = ["-ss", f"{seek_start:.6f}"] if seek_start > 0 else []

    def ff(cmd: list[str], what: str) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr[-2000:], file=sys.stderr)
            raise RuntimeError(f"ffmpeg splice {what} failed")

    # VIDEO: one decode, per-frame keep-test (select), re-stamp to drop gaps. fps normalizes CFR.
    # End-exclusive selection prevents a duplicated frame at joins. The PTS expression maps every
    # kept frame to its source-relative position inside the gapless output, so frame rounding cannot
    # accumulate one whole frame of duration at every cut.
    expr, video_pts = build_video_timeline(local_segments)
    if scale:
        sw, sh = scale
        vscale = (f",scale={sw}:{sh}:force_original_aspect_ratio=decrease,"
                  f"pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    else:
        vscale = ""
    # no_audio: video-only output (e.g. a co-spliced SCREEN track whose audio the composite discards).
    # Skips the audio + mux passes entirely — the expensive part on a 4K screen decode.
    vtarget = out if no_audio else vtmp
    ff(["ffmpeg", "-y", *input_args, "-i", str(src), "-t", f"{seek_duration:.6f}",
        "-map", "0:v:0", "-an",
        "-vf", f"fps={fps},select='{expr}',setpts='{video_pts}'{vscale}",
        "-fps_mode", "vfr",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-movflags", "+faststart", str(vtarget)], "video")
    if no_audio:
        return

    # AUDIO: decode once, route each frame to one segment, de-click joins, then concatenate. This is
    # linear in input frames; the old N-way atrim graph evaluated every frame against every segment.
    afc, audio_output = build_audio_filter(local_segments, xfade)
    ff(["ffmpeg", "-y", *input_args, "-i", str(src), "-t", f"{seek_duration:.6f}",
        "-vn", "-filter_complex", afc, "-map", audio_output,
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
    ap.add_argument("--silence-db", type=float, default=-27.0,
                    help="silencedetect noise floor in dB (dead-air detection)")
    ap.add_argument("--max-gap", type=float, default=0.28,
                    help="hard ceiling on any internal gap inside a kept span, seconds (dead-air kill)")
    ap.add_argument("--retake-window", type=float, default=3.0,
                    help="window (s) for IMMEDIATE stutter/false-start detection — keep small (~3s); "
                         "wide-gap retakes go through --drop, not this scan")
    ap.add_argument(
        "--no-auto-retakes",
        action="store_true",
        help="disable legacy n-gram guesses; V3 uses host-resolved Editorial Review Ledger drops",
    )
    ap.add_argument("--drop", default=None,
                    help="JSON file of explicit source-second spans to remove: "
                         "[[a,b],...] or {\"explicit_drops\":[{\"span\":[a,b]},...]}")
    ap.add_argument("--segments", default=None,
                    help="reuse the exact segments from a prior .segments.json (co-splice a screen track)")
    ap.add_argument("--scale", default=None,
                    help="WxH — downscale each cut segment (e.g. 1920x1080 for a 4K screen track)")
    ap.add_argument("--no-audio", action="store_true",
                    help="video-only output (skip the audio+mux passes) — for a co-spliced screen "
                         "track whose audio the composite discards; big speedup on a 4K decode")
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

    retakes: list[dict] = []
    explicit: list[list[float]] = []
    if args.segments:
        # co-splice mode: reuse the EXACT sub-segments a prior run computed (keeps a screen track
        # frame-synced with the camera that owns the silence-driven cut). Retake/drop excision
        # already happened on the camera pass — its segments carry the drops, so we reuse verbatim.
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
        # Retake removal wired INTO the cut: excise the earlier of each adjacent near-duplicate
        # phrase (last-take bias) plus any explicit surgical drops, BEFORE gap-tightening.
        retakes = (
            []
            if args.no_auto_retakes
            else detect_retakes(words, window_s=args.retake_window, sacred=sacred)
        )
        if args.drop:
            dd = load(args.drop)
            raw = dd.get("explicit_drops", []) if isinstance(dd, dict) else dd
            for item in raw:
                if isinstance(item, dict) and "span" in item:
                    explicit.append([float(item["span"][0]), float(item["span"][1])])
                elif isinstance(item, (list, tuple)) and len(item) == 2:
                    explicit.append([float(item[0]), float(item[1])])
        drop_spans = [d["span"] for d in retakes] + explicit
        if drop_spans:
            keep = subtract_spans(keep, drop_spans)
            if not keep:
                print("ERROR: all keep spans removed by drops — check --drop / retake window.",
                      file=sys.stderr)
                return 3
        silences = detect_silences(Path(args.inp), args.silence_db, min(threshold, args.max_gap))
        segments = compute_segments(keep, words, sacred, threshold, target, silences, args.max_gap)
        if not segments:
            print("ERROR: computed zero segments — check keep spans vs word timings.", file=sys.stderr)
            return 3

    out = Path(args.out)
    render(Path(args.inp), segments, out, args.xfade, scale, no_audio=args.no_audio)

    kept = round(sum(e - s for s, e in segments), 2)
    (out.parent / (out.stem + ".segments.json")).write_text(
        json.dumps({"segments": segments, "kept_seconds": kept,
                    "gap_threshold": threshold, "gap_target": target,
                    "max_gap": args.max_gap, "silence_db": args.silence_db,
                    "retakes_dropped": retakes,
                    "explicit_drops": [{"span": s} for s in explicit]}, indent=1))
    print(json.dumps({"event": "spliced", "segments": len(segments), "kept_seconds": kept,
                      "retakes_dropped": len(retakes), "explicit_drops": len(explicit),
                      "out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
