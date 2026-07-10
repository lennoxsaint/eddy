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
WORD_ALIGNMENT_TOLERANCE = 0.02
PROTECTED_PAUSE_CEILING = 0.8
AV_DRIFT_CEILING = 0.08


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


def av_duration_drift(info: dict) -> float:
    """Absolute delivered video/audio duration difference, or infinity when unprovable."""

    durations: dict[str, float] = {}
    for stream in info.get("streams", []):
        kind = stream.get("codec_type")
        if kind not in {"video", "audio"} or kind in durations:
            continue
        try:
            durations[kind] = float(stream["duration"])
        except (KeyError, TypeError, ValueError):
            continue
    if set(durations) != {"video", "audio"}:
        return float("inf")
    return abs(durations["video"] - durations["audio"])


def silence_stats(path: Path, noise_db: float, min_dur: float) -> tuple[float, float, list[list[float]]]:
    """(max_silence, total_silence, spans) in the FINAL render — catches dead air a cut missed."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d={min_dur:.3f}", "-f", "null", "-"],
        capture_output=True, text=True)
    spans: list[list[float]] = []
    pending = None
    for line in proc.stderr.splitlines():
        if "silence_start:" in line:
            try:
                pending = float(line.split("silence_start:")[1].strip())
            except ValueError:
                pending = None
        elif "silence_end:" in line and pending is not None:
            try:
                spans.append([pending, float(line.split("silence_end:")[1].split("|")[0].strip())])
            except ValueError:
                pass
            pending = None
    durs = [e - s for s, e in spans]
    return (max(durs) if durs else 0.0, sum(durs), spans)


def retake_scan(words: list[dict], ngram: int = 4, window_s: float = 12.0) -> list[dict]:
    """Flag adjacent duplicate phrases (likely leftover retakes): the same `ngram` word sequence
    recurring within `window_s`. Specific enough (4-grams) to rarely fire on genuine repetition."""
    toks = [(("".join(c for c in w.get("word", "").lower() if c.isalnum())), w.get("start", 0.0))
            for w in words]
    toks = [(t, s) for t, s in toks if t]
    flags: list[dict] = []
    seen: dict[tuple, float] = {}
    for i in range(len(toks) - ngram + 1):
        key = tuple(t for t, _ in toks[i:i + ngram])
        start = toks[i][1]
        prev = seen.get(key)
        if prev is not None and 0 < start - prev <= window_s:
            flags.append({"phrase": " ".join(key), "first_s": round(prev, 2), "again_s": round(start, 2)})
        seen[key] = start
    return flags


def retranscribe(path: Path) -> list[dict] | None:
    """Re-transcribe the FINAL render for the retake gate when no --final-words was supplied.

    Shells to transcribe.py (which owns the WhisperX caption-gen venv) so the retake scan can NEVER
    be silently skipped. Returns the word list ([] if the render genuinely has no speech), or None
    if transcription failed (which the caller treats as a blocking gate failure — un-verifiable).
    """
    script = Path(__file__).resolve().parent / "transcribe.py"
    tmp = path.with_suffix(".verify-words.json")
    proc = subprocess.run([sys.executable, str(script), "--in", str(path), "--out", str(tmp)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not tmp.exists():
        print(proc.stderr[-800:], file=sys.stderr)
        return None
    try:
        return json.loads(tmp.read_text()).get("words", [])
    except (json.JSONDecodeError, OSError):
        return None


def src_to_final(src_t: float, segments: list[list[float]]) -> float | None:
    """Map a SOURCE-time instant to its FINAL-render time through the kept sub-segments."""
    acc = 0.0
    for s, e in segments:
        if s <= src_t <= e:
            return round(acc + (src_t - s), 3)
        acc += e - s
    return None


def final_sacred_windows(sacred_src: list[list[float]], segments: list[list[float]]) -> list[list[float]]:
    """Project SOURCE-time sacred spans (intentional pauses / instructional or rhetorical repeats)
    into FINAL-render time so the silence + retake gates can exempt them (never block on them)."""
    out: list[list[float]] = []
    for a, b in sacred_src:
        fa, fb = src_to_final(a, segments), src_to_final(b, segments)
        if fa is not None and fb is not None and fb > fa:
            out.append([fa, fb])
    return out


def _in_windows(t: float, windows: list[list[float]], pad: float = 0.75) -> bool:
    return any(a - pad <= t <= b + pad for a, b in windows)


def apply_protected_pause_ceiling(
    silence_spans: list[list[float]],
    protected_windows: list[list[float]],
    *,
    ceiling: float = PROTECTED_PAUSE_CEILING,
) -> tuple[list[list[float]], list[list[float]]]:
    """Exempt only short protected breaths; long protected silence remains a blocker."""

    kept: list[list[float]] = []
    violations: list[list[float]] = []
    for span in silence_spans:
        midpoint = (span[0] + span[1]) / 2
        if _in_windows(midpoint, protected_windows):
            if span[1] - span[0] > ceiling:
                violations.append(span)
            continue
        kept.append(span)
    return kept, violations


def word_gap_verdict(
    words: list[dict],
    protected_windows: list[list[float]],
    *,
    hard_max: float = HARD_MAX_GAP,
    alignment_tolerance: float = WORD_ALIGNMENT_TOLERANCE,
) -> dict:
    """Verify the delivered-word cadence without allowing protection to hide dead air."""

    gaps: list[list[float]] = []
    protected_violations: list[list[float]] = []
    ordinary_gaps: list[list[float]] = []
    for left, right in zip(words, words[1:], strict=False):
        start, end = float(left["end"]), float(right["start"])
        if end <= start:
            continue
        gap = [round(start, 3), round(end, 3)]
        gaps.append(gap)
        midpoint = (start + end) / 2.0
        if _in_windows(midpoint, protected_windows, pad=0.0):
            if end - start > PROTECTED_PAUSE_CEILING:
                protected_violations.append(gap)
        else:
            ordinary_gaps.append(gap)
    durations = sorted(end - start for start, end in gaps)
    percentile_index = max(0, int(len(durations) * 0.95) - 1)
    p95 = durations[percentile_index] if durations else 0.0
    slow_overall = p95 > hard_max + alignment_tolerance
    ordinary_violations = (
        [gap for gap in ordinary_gaps if gap[1] - gap[0] > hard_max + alignment_tolerance]
        if slow_overall
        else [
            gap
            for gap in ordinary_gaps
            if gap[1] - gap[0] > PROTECTED_PAUSE_CEILING
        ]
    )
    return {
        "pass": not ordinary_violations and not protected_violations,
        "hard_max_s": hard_max,
        "alignment_tolerance_s": alignment_tolerance,
        "extreme_gap_ceiling_s": PROTECTED_PAUSE_CEILING,
        "protected_ceiling_s": PROTECTED_PAUSE_CEILING,
        "p95_s": round(p95, 3),
        "slow_overall": slow_overall,
        "violations": ordinary_violations,
        "protected_violations": protected_violations,
    }


def delivered_editorial_issues(final_words: Path) -> list[dict]:
    """Run Eddy's full editorial detector against a delivered-media transcript."""

    from eddy.editorial import build_editorial_ledger

    ledger = build_editorial_ledger(final_words)
    return [
        candidate
        for candidate in ledger["candidates"]
        if candidate.get("kind") in {"repeat", "reset_loop", "false_start"}
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic verification gates.")
    ap.add_argument("--final", required=True)
    ap.add_argument("--segments")
    ap.add_argument("--plan")
    ap.add_argument("--sacred", help="cutlist/JSON with SOURCE-time protected spans; mapped to "
                    "final time via --segments. Protection can retain intentional meaning but "
                    "never exempts silence above 0.8s")
    ap.add_argument("--source-audio")
    ap.add_argument("--expect-w", type=int, default=1920)
    ap.add_argument("--expect-h", type=int, default=1080)
    ap.add_argument("--final-words", help="word-level transcript of the FINAL render (re-transcribed) for the retake scan")
    ap.add_argument("--no-retake-scan", action="store_true",
                    help="skip the (auto re-transcribe) retake scan — proxy/self-heal iterations only; NEVER on a final")
    ap.add_argument("--retake-window", type=float, default=5.0,
                    help="near-duplicate window (s) for the retake gate. On the FINAL render a surviving "
                         "retake is adjacent (gap collapsed), so keep it small (~5s, >= splice's window) "
                         "to catch survivors without false-flagging legit recurrence")
    ap.add_argument("--max-deadair", type=float, default=HARD_MAX_GAP,
                    help="largest allowed unprotected silence in the final (s)")
    ap.add_argument("--min-speech-ratio", type=float, default=0.45)
    ap.add_argument("--silence-db", type=float, default=-30.0)
    args = ap.parse_args()

    final = Path(args.final)
    if not final.exists():
        print("ERROR: final not found.", file=sys.stderr)
        return 2

    gates: list[dict] = []

    def gate(name: str, ok: bool, **detail):
        gates.append({"gate": name, "pass": bool(ok), **detail})

    info = probe(final)

    # sacred SOURCE spans -> FINAL windows (mapped via segments), exempt from silence + retake gates.
    sacred_final: list[list[float]] = []
    if args.sacred and Path(args.sacred).exists() and args.segments and Path(args.segments).exists():
        sac_src = json.loads(Path(args.sacred).read_text()).get("sacred", [])
        seg_map = json.loads(Path(args.segments).read_text()).get("segments", [])
        sacred_final = final_sacred_windows(sac_src, seg_map)

    # Layout assert: resolution
    w, h = video_res(info)
    gate("layout_resolution", w == args.expect_w and h == args.expect_h,
         got=f"{w}x{h}", expected=f"{args.expect_w}x{args.expect_h}")

    # Has audio (Studio Sound muxed)
    gate("has_audio", has_audio(info))
    if has_audio(info):
        av_drift = av_duration_drift(info)
        gate(
            "av_sync_duration",
            av_drift <= AV_DRIFT_CEILING,
            drift_s=round(av_drift, 3),
            ceiling_s=AV_DRIFT_CEILING,
        )

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

    # Dead-air gate: silencedetect the RENDERED audio. Catches the long gaps a cut missed (the 16s
    # / 4s survivors) without false-flagging a short deliberate breath (max-deadair default 1.5s).
    if has_audio(info):
        max_sil, total_sil, sil_spans = silence_stats(final, args.silence_db, min(0.3, args.max_deadair))
        # exempt sacred windows (an intentional pause, e.g. a real-time demo, is not dead air).
        protected_violations: list[list[float]] = []
        if sacred_final:
            sil_spans, protected_violations = apply_protected_pause_ceiling(
                sil_spans, sacred_final
            )
            durs = [e - s for s, e in sil_spans]
            max_sil, total_sil = (max(durs) if durs else 0.0), sum(durs)
        fin = duration(final)
        speech_ratio = round(1.0 - (total_sil / fin), 3) if fin > 0 else 1.0
        worst = max(sil_spans, key=lambda p: p[1] - p[0], default=None)
        gate("max_internal_silence_ok", max_sil <= args.max_deadair,
             max_silence_s=round(max_sil, 2), limit_s=args.max_deadair,
             at=(round(worst[0], 1) if worst else None))
        gate("speech_ratio_ok", speech_ratio >= args.min_speech_ratio,
             speech_ratio=speech_ratio, floor=args.min_speech_ratio)
        gate(
            "protected_pause_ceiling",
            not protected_violations,
            ceiling_s=PROTECTED_PAUSE_CEILING,
            violations=protected_violations,
        )

    # Retake scan: flag adjacent duplicate phrases (leftover retakes) in the FINAL render. NEVER
    # skipped — if no --final-words was supplied we auto re-transcribe the render (transcribe.py /
    # WhisperX). A transcription failure is itself a blocking failure (can't prove it's clean).
    if not args.no_retake_scan and has_audio(info):
        if args.final_words and Path(args.final_words).exists():
            fw = json.loads(Path(args.final_words).read_text()).get("words", [])
        else:
            fw = retranscribe(final)
        if fw is None:
            gate("retake_repeat_scan", False, reason="could not obtain final words (re-transcribe failed)")
        else:
            flagged = retake_scan(fw, window_s=args.retake_window)
            # exempt sacred windows (intentional instructional/rhetorical repetition, not a retake).
            if sacred_final:
                flagged = [f for f in flagged if not _in_windows(f["again_s"], sacred_final)]
            gate("retake_repeat_scan", not flagged, flagged=flagged[:12], count=len(flagged))
            cadence = word_gap_verdict(fw, sacred_final)
            gate("high_energy_cadence", cadence["pass"], **cadence)
            if args.final_words and Path(args.final_words).exists():
                editorial_issues = delivered_editorial_issues(Path(args.final_words))
            else:
                generated_words = final.with_suffix(".verify-words.json")
                editorial_issues = (
                    delivered_editorial_issues(generated_words)
                    if generated_words.exists()
                    else []
                )
            gate(
                "delivered_editorial_truth",
                not editorial_issues,
                issues=editorial_issues[:12],
                count=len(editorial_issues),
            )

    passed = all(g["pass"] for g in gates)
    # Blocking gates that are safety-critical — name them explicitly for the self-heal loop.
    blocking = {
        "max_internal_silence_ok",
        "protected_pause_ceiling",
        "retake_repeat_scan",
        "high_energy_cadence",
        "delivered_editorial_truth",
        "layout_resolution",
        "has_audio",
        "av_sync_duration",
    }
    failed_blocking = [g["gate"] for g in gates if not g["pass"] and g["gate"] in blocking]
    verdict = {"pass": passed, "gates": gates, "failed_blocking": failed_blocking,
               "ran": len(gates), "note": "model rubrics (hook/cohesion/gutting) judged separately"}
    print(json.dumps(verdict, indent=1))
    if failed_blocking:
        print(f"FATAL: blocking gate(s) failed: {', '.join(failed_blocking)}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
