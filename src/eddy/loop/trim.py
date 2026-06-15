"""v0.3.2 deterministic trim-to-fit: a guarded last-resort CUTTING backstop for the residual gap
to the length ceiling that the model-driven loop couldn't close.

The model-first loop (feasibility-gated plateau + escalating directive + density up-front) is the
primary fix for the 33-39min floor. This pass is the backstop for the rare case where the model
genuinely cannot reach the ceiling by cutting — it removes WHOLE lowest-value beats (long,
fast-narrated 'reading the screen aloud' read-throughs) and then RE-JUDGES the result, reverting
wholesale if the cut regressed. Cutting is semantic and dangerous (a blind removal can orphan a
payoff or break a splice), so unlike speed-to-fit this pass never trusts itself: it ships its trim
ONLY if the full judge + ship panel + deterministic gates all clear vs the pre-trim cut.

Off by default (enable_aggressive_trim). When both backstops are on it runs BEFORE speed-to-fit —
exhaust cutting before speeding, since removing dead weight beats rushing kept content.

Eligibility mirrors speed.py's protected vocabulary: never a beat overlapping a protected_moment or
labeled hook/payoff/outro/CTA/cold_open. Granularity is whole beats only — beat boundaries are
semantic units, the safest grain for a mechanical pass.
"""

from __future__ import annotations

import json
from pathlib import Path

from eddy.edit.compiler import cut_transcript
from eddy.edit.schema import Edl, EditDecisions
from eddy.qa.quality import _HOOK_LABELS, _OUTRO_LABELS, _PAYOFF_LABELS

# a beat carrying any of these tokens is structurally important — never remove it (same as speed.py)
_PROTECTED_LABEL_TOKENS = (*_HOOK_LABELS, *_OUTRO_LABELS, *_PAYOFF_LABELS, "cold_open")


def _recompute_total(ranges) -> float:
    return round(sum((r.end - r.start) / (r.speed or 1.0) for r in ranges), 2)


def _removable_beats(edl: Edl, decisions: EditDecisions, phrases: list[dict]) -> list[dict]:
    """Highest-value-to-remove first: {label, range_idxs, reclaim_s, score}. A long span narrated
    fast (high wpm * output seconds) is a screen read-through — the lowest editorial value per
    second and the safest whole-beat removal. Excludes protected-label beats, the cold-open clip,
    and any beat whose ranges overlap a protected_moment."""
    kept = cut_transcript(edl, phrases)
    pms = decisions.protected_moments
    used: set[int] = set()
    out: list[dict] = []
    for beat in decisions.x_eddy.beats:
        label = beat.get("label") or ""
        if any(tok in label.lower() for tok in _PROTECTED_LABEL_TOKENS):
            continue
        bs, be = beat.get("start_s", 0.0), beat.get("end_s", 0.0)
        if be <= bs:
            continue
        idxs: list[int] = []
        for i, r in enumerate(edl.ranges):
            if i in used:
                continue
            if (r.beat or "").upper() == "COLD_OPEN":
                continue
            mid = (r.start + r.end) / 2
            if not (bs <= mid < be):
                continue
            if any(r.start < pm.end_s and r.end > pm.start_s for pm in pms):
                continue  # range overlaps protected content
            idxs.append(i)
        if not idxs:
            continue
        used.update(idxs)
        reclaim_s = sum((edl.ranges[i].end - edl.ranges[i].start) / (edl.ranges[i].speed or 1.0) for i in idxs)
        if reclaim_s <= 0:
            continue
        in_beat = [p for p in kept if bs <= p["start"] < be]
        kept_s = sum(p["out_end"] - p["out_start"] for p in in_beat)
        nwords = sum(len(p["text"].split()) for p in in_beat)
        wpm = (nwords / kept_s * 60) if kept_s > 0 else 0.0
        out.append({"label": label, "range_idxs": idxs, "reclaim_s": reclaim_s, "score": wpm * reclaim_s})
    out.sort(key=lambda b: b["score"], reverse=True)
    return out


def _baseline(chosen: Path) -> tuple[float, int, bool]:
    """Pre-trim judge weighted, major-defect count, and stability from the chosen iteration."""
    try:
        j = json.loads((chosen / "judge.json").read_text())
        majors = sum(1 for d in j.get("defects", []) if d.get("severity") == "major")
        return float(j.get("weighted", 0.0)), majors, bool(j.get("judge_unstable"))
    except Exception:
        return 0.0, 0, True


def trim_to_fit(
    edl: Edl,
    decisions: EditDecisions,
    sim_report: dict,
    run_dir: Path,
    chosen: Path,
    provider,
    receipts,
    cfg,
) -> dict:
    """Mutate `edl` in place ONLY if a whole-beat trim toward the ceiling passes the full re-judge.
    Returns an info dict for receipts/logging. No-op unless enable_aggressive_trim and over ceiling."""
    loop = cfg.loop
    ceiling = loop.length_ceiling_minutes * 60
    info = {
        "applied": False,
        "adopted": False,
        "enabled": loop.enable_aggressive_trim,
        "ceiling_s": round(ceiling, 1),
        "duration_before_s": edl.total_duration_s,
        "duration_after_s": edl.total_duration_s,
        "over_before_s": round(max(0.0, edl.total_duration_s - ceiling), 1),
        "ceiling_missed_s": round(max(0.0, edl.total_duration_s - ceiling), 1),
        "beats_dropped": [],
        "revert_reason": None,
    }
    if not loop.enable_aggressive_trim:
        return info
    over = edl.total_duration_s - ceiling
    if over <= 0:
        return info  # already under the ceiling — nothing to do

    from eddy.transcribe.pack import phrases as load_phrases

    phrases = load_phrases(run_dir)

    # greedy: remove whole lowest-value beats until we cross the ceiling (or run out of eligible
    # beats — best-effort, residual logged). Smallest set possible = fewest new splices.
    drop_idxs: list[int] = []
    dropped_meta: list[dict] = []
    reclaimed = 0.0
    for beat in _removable_beats(edl, decisions, phrases):
        if reclaimed >= over:
            break
        drop_idxs.extend(beat["range_idxs"])
        reclaimed += beat["reclaim_s"]
        dropped_meta.append({"label": beat["label"], "ranges": len(beat["range_idxs"]), "reclaim_s": round(beat["reclaim_s"], 1)})
    if not drop_idxs:
        info["revert_reason"] = "no eligible beats to remove"
        return info

    drop_set = set(drop_idxs)
    keep = [edl.ranges[i] for i in range(len(edl.ranges)) if i not in drop_set]
    if len(keep) < 1:
        # deterministic non-empty invariant — never rely on the render raising on an empty concat
        info["revert_reason"] = "trim would empty the edit"
        receipts.log("trim_to_fit", adopted=False, reason=info["revert_reason"])
        return info
    info["applied"] = True
    trimmed = Edl(sources=dict(edl.sources), ranges=keep, total_duration_s=_recompute_total(keep))

    # validate ONCE: re-simulate, render a throwaway proxy, run the full deterministic gates + judge
    # + ship panel. Cutting is semantic, so this pass never trusts itself — it adopts only on a clean
    # bill of health vs the pre-trim cut, else reverts wholesale.
    from eddy.edit.simulate import simulate
    from eddy.qa.deterministic import run_deterministic
    from eddy.qa.judge import run_judge, run_ship_panel
    from eddy.render.segments import render_edl

    target_s = sim_report.get("target_s", loop.default_target_minutes * 60)
    base_w, base_majors, base_unstable = _baseline(chosen)
    try:
        t_sim = simulate(trimmed, decisions, phrases, cfg, target_s)
        # render the validation proxy under iterations/ (internal scratch), never into the
        # deliverables final/ folder
        proxy = run_dir / "iterations" / "trim-proxy.mp4"
        render_edl(trimmed, proxy, run_dir, cfg.render, receipts=receipts, proxy=True)
        t_qa = run_deterministic(proxy, trimmed, run_dir, cfg, sim_report=t_sim, protected_count=len(decisions.protected_moments))
        t_kept = cut_transcript(trimmed, phrases)
        t_judge = run_judge(provider, receipts, t_sim, decisions, trimmed, t_kept, cfg)
        t_panel = run_ship_panel(provider, receipts, t_sim, decisions, trimmed, t_kept, cfg)
    except Exception as e:
        info["revert_reason"] = f"validation error: {str(e)[:160]}"
        receipts.log("trim_to_fit", adopted=False, reason=info["revert_reason"])
        return info

    t_majors = sum(1 for d in t_judge.get("defects", []) if d.get("severity") == "major")
    checks = {
        "gates_pass": t_qa["pass"],
        "judge_stable": not t_judge.get("judge_unstable"),
        "judge_held": t_judge.get("weighted", 0.0) >= base_w - loop.trim_judge_tolerance,
        "panel_ships": t_panel.get("ships", False),
        "no_new_majors": t_majors <= base_majors,
    }
    if all(checks.values()):
        edl.ranges = list(trimmed.ranges)
        edl.total_duration_s = trimmed.total_duration_s
        info["adopted"] = True
        info["beats_dropped"] = dropped_meta
        info["duration_after_s"] = trimmed.total_duration_s
        info["ceiling_missed_s"] = round(max(0.0, trimmed.total_duration_s - ceiling), 1)
    else:
        info["revert_reason"] = "regressed: " + ", ".join(k for k, v in checks.items() if not v)

    receipts.log(
        "trim_to_fit", adopted=info["adopted"], beats_dropped=len(dropped_meta),
        duration_before_s=info["duration_before_s"], duration_after_s=info["duration_after_s"],
        ceiling_missed_s=info["ceiling_missed_s"], reason=info["revert_reason"],
        baseline_judge=round(base_w, 2), trimmed_judge=round(t_judge.get("weighted", 0.0), 2),
    )
    return info
