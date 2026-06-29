"""Tier-0 QA: simulate the edit from the EDL without rendering anything.

Produces sim-report.json: cut transcript, boundary cards, gap stats, duration —
and the sim-QA verdicts the loop gates on before any render."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import EddyConfig
from eddy.edit.compiler import cut_transcript, cut_word_transcript
from eddy.edit.kernel import retake_clean_failures
from eddy.edit.schema import EditDecisions, Edl


def boundary_cards(edl: Edl, phrases: list[dict]) -> list[dict]:
    """One card per splice: text running into the cut, what was removed, text out."""
    cards = []
    for left, right in zip(edl.ranges, edl.ranges[1:]):
        # a cold-open is a deliberate reorder (right precedes left in source time); it is a
        # hard cut by design, not a splice to evaluate for continuity
        if right.start < left.start:
            continue
        before = [p["text"] for p in phrases if p["end"] <= left.end + 0.05][-2:]
        removed = [p["text"] for p in phrases if left.end - 0.05 < p["start"] and p["end"] < right.start + 0.05]
        after = [p["text"] for p in phrases if p["start"] >= right.start - 0.05][:2]
        removed_text = " ".join(removed)
        cards.append(
            {
                "splice_at_source_s": round(left.end, 2),
                "removed_s": round(right.start - left.end, 2),
                "before_text": " ".join(before)[-220:],
                "removed_summary": (removed_text[:120] + "…" + removed_text[-60:]) if len(removed_text) > 200 else removed_text,
                "after_text": " ".join(after)[:220],
                "start_handle_s": right.start_handle_s,
                "end_handle_s": left.end_handle_s,
            }
        )
    return cards


def raw_beat_density(beats: list[dict], phrases: list[dict]) -> list[dict]:
    """Pre-cut per-beat density: source span_s + raw words-per-minute, heaviest-first.

    Unlike the post-cut beat_density (which needs a compiled EDL), this reads the raw transcript
    against the beat map, so it can be handed to the model at iteration 1 — before any cut exists —
    to flag the long, low-density 'reading the screen aloud' runs that are the structural-cut
    candidates. A LOW raw_wpm over a LONG span_s is the signature of a draggy, compressible beat."""
    out: list[dict] = []
    for beat in beats:
        bs, be = beat.get("start_s", 0.0), beat.get("end_s", 0.0)
        span = be - bs
        if span <= 0:
            continue
        in_beat = [p for p in phrases if bs <= p["start"] < be]
        nwords = sum(len(p["text"].split()) for p in in_beat)
        wpm = round(nwords / span * 60, 1) if span > 0 else 0.0
        out.append({"label": beat.get("label", ""), "span_s": round(span, 1), "raw_wpm": wpm})
    out.sort(key=lambda b: b["span_s"], reverse=True)
    return out


def latest_post_cut_density(run_dir: Path) -> list[dict]:
    """The most recent iteration's post-cut beat density (kept_s + wpm per beat), or [] if none yet.

    The revise loop uses this to show the model the pacing its LAST cuts actually produced, instead of
    re-sending the pre-cut raw density every pass — so it can see whether a draggy beat got tighter."""
    reports = sorted((Path(run_dir) / "iterations").glob("*/sim-report.json"))
    if not reports:
        return []
    try:
        return json.loads(reports[-1].read_text()).get("beat_density", []) or []
    except (OSError, json.JSONDecodeError):
        return []


def simulate(
    edl: Edl,
    decisions: EditDecisions,
    phrases: list[dict],
    cfg: EddyConfig,
    target_s: float,
    words: list[dict] | None = None,
) -> dict:
    kept = cut_transcript(edl, phrases)
    word_kept = cut_word_transcript(edl, words) if words else []
    kept_for_gates = word_kept or kept
    cards = boundary_cards(edl, phrases)
    retake_failures = retake_clean_failures(kept_for_gates)

    # dead air remaining inside keep ranges — silence inside a protected moment is
    # a deliberate visual beat (demo footage), not a defect. The exception is NARROW:
    # the protected span must explicitly cover the silence, not merely sit within ~1s,
    # so "mouth moving, no sound" can no longer hide behind a nearby protection.
    dead_air = []
    for a, b in zip(kept_for_gates, kept_for_gates[1:]):
        gap = b["out_start"] - a["out_end"]
        if gap > cfg.gates.max_dead_air_s:
            src = a["end"]  # raw-timeline end of the phrase before the gap
            protected = any(pm.start_s <= src <= pm.end_s for pm in decisions.protected_moments)
            if not protected:
                dead_air.append({"after_out_s": a["out_end"], "gap_s": round(gap, 2), "before": a["text"][-60:]})

    # Word-onset safety is an editorial gate, not just a render nicety. A 30ms fade can hide a pop,
    # but it cannot restore a shaved first syllable, so sub-floor handles now fail the sim.
    FADE_FLOOR_S = 0.03
    thin_handles = [
        c for c in cards
        if 0 < c["start_handle_s"] < FADE_FLOOR_S or 0 < c["end_handle_s"] < FADE_FLOOR_S
    ]
    handle_warnings = [
        c for c in cards
        if FADE_FLOOR_S <= c["start_handle_s"] < cfg.gates.min_boundary_handle_s
        or FADE_FLOOR_S <= c["end_handle_s"] < cfg.gates.min_boundary_handle_s
    ]

    # beat density: kept seconds + words-per-minute per beat. Long beats are the
    # structural-cut candidates when over target; sustained fast WPM flags "reading the
    # screen aloud" runs the editorial brain should compress to the essential items.
    beat_density = []
    for beat in decisions.x_eddy.beats:
        bs, be = beat.get("start_s", 0), beat.get("end_s", 0)
        in_beat = [p for p in kept if bs <= p["start"] < be]
        if not in_beat:
            continue
        kept_s = sum(p["out_end"] - p["out_start"] for p in in_beat)
        nwords = sum(len(p["text"].split()) for p in in_beat)
        wpm = round(nwords / kept_s * 60, 1) if kept_s > 0 else 0
        beat_density.append({"label": beat.get("label", ""), "kept_s": round(kept_s, 1), "wpm": wpm})
    beat_density.sort(key=lambda b: b["kept_s"], reverse=True)

    duration = edl.total_duration_s
    lo, hi = cfg.loop.duration_band
    ceiling_s = cfg.loop.length_ceiling_minutes * 60
    # v0.3: duration is NO LONGER a gate. The loop maximizes quality with length as a
    # ceiling constraint, so an over-ceiling iteration must still pass deterministic gates
    # (otherwise the loop could never report "done" and would best-attempt at the cap every
    # run). under_ceiling is advisory — it drives the compression directive, not pass/fail.
    verdicts = {
        "no_dead_air": not dead_air,
        "handles_safe": not thin_handles and not handle_warnings,
        "retake_clean": not retake_failures,
        "has_content": len(kept) > 0,
    }

    report = {
        "duration_s": duration,
        "target_s": target_s,
        "band_s": [round(lo * target_s, 1), round(hi * target_s, 1)],
        "ceiling_s": round(ceiling_s, 1),
        "under_ceiling": duration <= ceiling_s,
        "duration_in_band": lo * target_s <= duration <= hi * target_s,  # advisory only
        "kept_phrases": len(kept),
        "ranges": len(edl.ranges),
        "removed_total_s": round(sum(max(0.0, b.start - a.end) for a, b in zip(edl.ranges, edl.ranges[1:])), 1),
        "boundary_cards": cards,
        "beat_density": beat_density,
        "dead_air": dead_air,
        "thin_handles": thin_handles,
        "handle_warnings": len(handle_warnings),
        "word_onset_safety": {
            "pass": not thin_handles and not handle_warnings,
            "thin_handles": thin_handles,
            "handle_warnings": handle_warnings,
            "minimum_handle_s": cfg.gates.min_boundary_handle_s,
        },
        "retake_clean": {
            "pass": not retake_failures,
            "failures": retake_failures,
        },
        "verdicts": verdicts,
        "pass": all(verdicts.values()),
    }
    return report


def save_report(report: dict, iter_dir: Path) -> Path:
    path = Path(iter_dir) / "sim-report.json"
    path.write_text(json.dumps(report, indent=1))
    return path
