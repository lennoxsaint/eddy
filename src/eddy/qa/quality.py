"""v0.3 hybrid quality metric: 0.6*objective(deterministic) + 0.4*critic(LLM), on 0-10.

The objective half is built ONLY from signals Eddy already computes (sim beat_density,
dead-air, duration) plus a deterministic transcript scan, so the model cannot game it and it is
monotonic in a defect count (adding a defect can never raise the score). The critic half is the
recalibrated, adversarial LLM judge (capped when unstable so it can't certify "done").

Length is a CONSTRAINT handled OUTSIDE this score (the loop's under_ceiling clean-ship check, the
over_ceiling_s ranking tiebreak, and the compression directive) — never folded into quality, so an
over-ceiling cut keeps a meaningful gradient instead of being zeroed. Being short earns nothing here.
"""

from __future__ import annotations

import re

from eddy.edit.protect import _RE as SETUP_RE
from eddy.edit.schema import EditDecisions

# Objective sub-weights — module-level to avoid config sprawl; must sum to 1.0.
OBJ_WEIGHTS = {
    "dead_air": 0.25,
    "pacing": 0.25,
    "orphan_refs": 0.20,
    "hook_present": 0.15,
    "closure_present": 0.15,
}

_CTA_RE = re.compile(
    r"\b(subscribe|comment below|leave a comment|link in|in the description|check out the|"
    r"join|sign ?up|next (?:video|time)|see you|thanks for watching|that'?s it for)\b",
    re.IGNORECASE,
)
_HOOK_LABELS = ("hook", "intro", "cold", "open")
_OUTRO_LABELS = ("outro", "cta", "close", "ending", "conclusion", "wrap", "recap")
_PAYOFF_LABELS = ("payoff", "demo", "result", "reveal", "answer", "verdict", "score")

DRAG_WPM = 200.0          # sustained words/min that reads as "narrating the screen"
DRAG_KEPT_S = 45.0        # ...over a long enough run to be a drag, not a quick aside
ORPHAN_GAP_S = 8.0        # source-time jump after a kept setup line ⇒ its payoff was cut
SLOW_START_FRAC = 0.15    # first payoff arriving past this fraction of the cut ⇒ slow start


def _beat_label_at(beats: list[dict], src_t: float) -> str:
    for b in beats:
        if b.get("start_s", 0) <= src_t < b.get("end_s", 0):
            return (b.get("label") or "").lower()
    return ""


def _orphan_count(kept: list[dict]) -> int:
    """Setup/transition line kept, but the payoff it introduces was cut right after it
    (a large source-time jump to the next kept phrase) ⇒ orphaned setup (the GPT-5.5 case)."""
    n = 0
    for a, b in zip(kept, kept[1:]):
        if SETUP_RE.search(a.get("text", "")) and (b["start"] - a["end"]) > ORPHAN_GAP_S:
            n += 1
    return n


def _signal_dead_air(sim: dict) -> float:
    n = len(sim.get("dead_air", []))
    return 10.0 * max(0.0, 1 - n / 3.0)  # 0 gaps=10, 3+=0


def _signal_pacing(sim: dict, kept: list[dict], decisions: EditDecisions) -> float:
    drag = sum(
        1 for bd in sim.get("beat_density", [])
        if bd.get("wpm", 0) > DRAG_WPM and bd.get("kept_s", 0) > DRAG_KEPT_S
    )
    score = 10.0 - 2.5 * drag
    # slow start: with no cold-open, the first payoff beat should land early in the cut
    if not decisions.cold_open and kept:
        dur = sim.get("duration_s", 0) or 1.0
        beats = decisions.x_eddy.beats
        first_payoff = next(
            (p["out_start"] for p in kept
             if any(lbl in _beat_label_at(beats, p["start"]) for lbl in _PAYOFF_LABELS)),
            None,
        )
        if first_payoff is not None and first_payoff > SLOW_START_FRAC * dur:
            score -= 3.0
    return max(0.0, score)


def _signal_orphans(kept: list[dict]) -> float:
    return 10.0 * max(0.0, 1 - _orphan_count(kept) / 2.0)


def _signal_hook(decisions: EditDecisions, kept: list[dict]) -> float:
    if decisions.cold_open:
        return 10.0
    if kept:
        first = kept[0]
        lbl = _beat_label_at(decisions.x_eddy.beats, first["start"])
        if first.get("out_start", 99) < 1.0 and any(h in lbl for h in _HOOK_LABELS):
            return 10.0
    return 4.0  # absent hook is recoverable, not catastrophic — floor not zero


def _signal_closure(kept: list[dict], decisions: EditDecisions) -> float:
    if not kept:
        return 4.0
    last = max(kept, key=lambda p: p.get("out_end", 0))
    lbl = _beat_label_at(decisions.x_eddy.beats, last["start"])
    if any(o in lbl for o in _OUTRO_LABELS) or _CTA_RE.search(last.get("text", "")):
        return 10.0
    return 4.0


def quality_score(sim: dict, judge: dict, kept: list[dict], decisions: EditDecisions,
                  phrases: list[dict], cfg, ceiling_minutes: float | None = None) -> dict:
    """Hybrid EDIT-quality score: 0.6*objective + 0.4*critic on 0-10 (locked decision #2).

    `ceiling_minutes` is the per-run resolved ceiling (e.g. from a parsed focus brief or a named
    format) — pass it so `over_ceiling_s` agrees with the loop's own ceiling. Defaults to the
    static `cfg.loop.length_ceiling_minutes` when the caller has no per-run ceiling on hand
    (matches every behavior before this parameter existed).

    Length is NOT part of this score — it is a separate CONSTRAINT enforced by the loop
    (the under_ceiling clean-ship requirement + the over_ceiling_s ranking tiebreak) and pushed
    by the compression directive. An earlier design subtracted a ceiling penalty here, but it
    saturated to 10 for any cut >2.5x the ceiling, zeroing quality for every over-ceiling
    iteration and destroying the gradient the loop needs. Keeping quality as pure edit quality
    means a 37-min cut and a 50-min cut are differentiated by how GOOD the edit is, while length
    is handled where it belongs."""
    comp = {
        "dead_air": _signal_dead_air(sim),
        "pacing": _signal_pacing(sim, kept, decisions),
        "orphan_refs": _signal_orphans(kept),
        "hook_present": _signal_hook(decisions, kept),
        "closure_present": _signal_closure(kept, decisions),
    }
    objective = sum(comp[k] * w for k, w in OBJ_WEIGHTS.items())

    # critic = LLM judge, but an unstable judge must not feed a real number that certifies done
    critic = judge.get("weighted", 0.0)
    if judge.get("judge_unstable"):
        critic = min(critic, 5.0)

    wo, wc = cfg.loop.quality_weight_objective, cfg.loop.quality_weight_critic
    quality = max(0.0, min(10.0, wo * objective + wc * critic))
    ceiling_s = (ceiling_minutes if ceiling_minutes is not None else cfg.loop.length_ceiling_minutes) * 60
    return {
        "quality": round(quality, 3),
        "objective": round(objective, 3),
        "critic": round(critic, 3),
        "over_ceiling_s": round(max(0.0, sim.get("duration_s", 0.0) - ceiling_s), 1),
        "components": {k: round(v, 2) for k, v in comp.items()},
    }
