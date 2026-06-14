"""Tier-0 QA: simulate the edit from the EDL without rendering anything.

Produces sim-report.json: cut transcript, boundary cards, gap stats, duration —
and the sim-QA verdicts the loop gates on before any render."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import EddyConfig
from eddy.edit.compiler import cut_transcript
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


def simulate(
    edl: Edl,
    decisions: EditDecisions,
    phrases: list[dict],
    cfg: EddyConfig,
    target_s: float,
) -> dict:
    kept = cut_transcript(edl, phrases)
    cards = boundary_cards(edl, phrases)

    # dead air remaining inside keep ranges — silence inside a protected moment is
    # a deliberate visual beat (demo footage), not a defect. The exception is NARROW:
    # the protected span must explicitly cover the silence, not merely sit within ~1s,
    # so "mouth moving, no sound" can no longer hide behind a nearby protection.
    dead_air = []
    for a, b in zip(kept, kept[1:]):
        gap = b["out_start"] - a["out_end"]
        if gap > cfg.gates.max_dead_air_s:
            src = a["end"]  # raw-timeline end of the phrase before the gap
            protected = any(pm.start_s <= src <= pm.end_s for pm in decisions.protected_moments)
            if not protected:
                dead_air.append({"after_out_s": a["out_end"], "gap_s": round(gap, 2), "before": a["text"][-60:]})

    # the 30ms boundary fade absorbs glued-word bleed: hard-fail only handles below
    # the fade floor; sub-min_boundary_handle handles are reported as warnings
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
        "handles_safe": not thin_handles,
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
        "verdicts": verdicts,
        "pass": all(verdicts.values()),
    }
    return report


def save_report(report: dict, iter_dir: Path) -> Path:
    path = Path(iter_dir) / "sim-report.json"
    path.write_text(json.dumps(report, indent=1))
    return path
