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

    duration = edl.total_duration_s
    lo, hi = cfg.loop.duration_band
    verdicts = {
        "duration_in_band": lo * target_s <= duration <= hi * target_s,
        "no_dead_air": not dead_air,
        "handles_safe": not thin_handles,
        "has_content": len(kept) > 0,
    }

    report = {
        "duration_s": duration,
        "target_s": target_s,
        "band_s": [round(lo * target_s, 1), round(hi * target_s, 1)],
        "kept_phrases": len(kept),
        "ranges": len(edl.ranges),
        "removed_total_s": round(sum(b.start - a.end for a, b in zip(edl.ranges, edl.ranges[1:])), 1),
        "boundary_cards": cards,
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
