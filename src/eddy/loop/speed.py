"""v0.3.1 speed-to-fit: deterministic time-compression to close a residual gap to the length
ceiling that cutting alone can't reach.

Across three v0.3 dogfoods the cut floored at ~33-39 min and never reached the 14-min ceiling —
the model cannot get there by removing more without gutting content. This pass runs ONCE, after
the cut-loop has converged on its best edit, and speeds up the heaviest SLOW, long, non-protected
beats (the "talking slowly over a long info-dump" runs) by the minimal factor needed. It is NOT a
model action: the editor already floored, so per the autoresearch discipline we trust a
deterministic mechanism, not a weak agent doing more. The existing ship panel reviews the result.

Eligibility (the safety rail) speeds a beat only if it is long (kept_s >= min_beat_s), slow
(wpm < max_wpm — fast beats are already paced and would turn unintelligible), not an important
beat (hook / outro-CTA / payoff label, reusing quality.py's vocabulary), not the cold-open clip,
and none of its ranges overlap a protected_moment. Factors are capped at speed_ramp_max_multiplier
(atempo preserves pitch, but past ~1.5x speech sounds rushed). If even max speed on every eligible
beat can't reach the ceiling, the edit ships best-effort with ceiling_missed_s logged — the ceiling
is a guardrail, never a reason to sacrifice protected content.
"""

from __future__ import annotations

from collections import defaultdict

from eddy.edit.schema import Edl, EditDecisions
from eddy.qa.quality import _HOOK_LABELS, _OUTRO_LABELS, _PAYOFF_LABELS

# a beat carrying any of these tokens is structurally important — never speed it
_PROTECTED_LABEL_TOKENS = (*_HOOK_LABELS, *_OUTRO_LABELS, *_PAYOFF_LABELS, "cold_open")


def _recompute_total(edl: Edl) -> float:
    return round(sum((r.end - r.start) / (r.speed or 1.0) for r in edl.ranges), 2)


def _eligible_beats(edl: Edl, decisions: EditDecisions, beat_density: list[dict], cfg) -> list[dict]:
    """Heaviest-first list of {label, range_idxs, span_s} that may be sped."""
    loop = cfg.loop
    # label -> list of source spans, in source order. A list (not a single value) so duplicate
    # beat labels each keep their own span instead of collapsing to the last one (which would
    # silently drop every earlier same-label beat from eligibility). Each beat_density row consumes
    # the next unused span for its label.
    spans: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for b in decisions.x_eddy.beats:
        spans[b.get("label") or ""].append((b.get("start_s", 0.0), b.get("end_s", 0.0)))
    span_cursor: dict[str, int] = defaultdict(int)
    pms = decisions.protected_moments
    used: set[int] = set()
    out: list[dict] = []
    # beat_density is already sorted by kept_s desc; re-sort defensively
    for bd in sorted(beat_density, key=lambda b: b.get("kept_s", 0.0), reverse=True):
        label = bd.get("label") or ""
        if not label:
            continue
        if bd.get("kept_s", 0.0) < loop.speed_ramp_min_beat_s:
            continue
        wpm = bd.get("wpm", 0.0)
        if wpm <= 0 or wpm >= loop.speed_ramp_max_wpm:
            continue  # only SLOW, long beats — fast ones are already paced
        low = label.lower()
        if any(tok in low for tok in _PROTECTED_LABEL_TOKENS):
            continue
        lst = spans.get(label, [])
        ci = span_cursor[label]
        if ci >= len(lst):
            continue  # more density rows than spans for this label — nothing left to map
        span_cursor[label] += 1
        bs, be = lst[ci]
        if be <= bs:
            continue
        idxs: list[int] = []
        for i, r in enumerate(edl.ranges):
            if i in used:
                continue
            if (r.beat or "").upper() == "COLD_OPEN":
                continue  # the reordered hook clip is never sped
            mid = (r.start + r.end) / 2
            if not (bs <= mid < be):
                continue
            if any(r.start < pm.end_s and r.end > pm.start_s for pm in pms):
                continue  # range overlaps protected content
            idxs.append(i)
        if not idxs:
            continue
        used.update(idxs)
        span_s = sum(edl.ranges[i].end - edl.ranges[i].start for i in idxs)
        if span_s <= 0:
            continue
        out.append({"label": label, "range_idxs": idxs, "span_s": span_s})
    return out


def speed_to_fit(edl: Edl, decisions: EditDecisions, beat_density: list[dict], cfg) -> dict:
    """Mutate `edl` in place: stamp EdlRange.speed on eligible beats to bring the output under the
    length ceiling, then recompute total_duration_s. Returns an info dict for receipts/logging.

    Pure aside from mutating edl (no I/O), so it is unit-testable without a render."""
    loop = cfg.loop
    info = {
        "applied": False,
        "enabled": loop.enable_speed_ramp,
        "ceiling_s": round(loop.length_ceiling_minutes * 60, 1),
        "duration_before_s": edl.total_duration_s,
        "duration_after_s": edl.total_duration_s,
        "over_before_s": 0.0,
        "ceiling_missed_s": 0.0,
        "beats_sped": [],
    }
    if not loop.enable_speed_ramp:
        return info

    ceiling = loop.length_ceiling_minutes * 60
    over = edl.total_duration_s - ceiling
    info["over_before_s"] = round(max(0.0, over), 1)
    if over <= 0:
        return info  # already under the ceiling — nothing to do

    cap = loop.speed_ramp_max_multiplier
    gap = over
    for beat in _eligible_beats(edl, decisions, beat_density, cfg):
        if gap <= 0:
            break
        S = beat["span_s"]
        max_save = S * (1.0 - 1.0 / cap)
        if gap <= max_save:
            factor = min(cap, S / (S - gap))  # close exactly the remaining gap
        else:
            factor = cap  # take the most this beat can give, keep going
        # clamp AFTER rounding so a non-clean cap (e.g. 1.41666) can't round UP past the cap and
        # trip the invariant assert below.
        factor = min(cap, round(max(1.0, factor), 3))
        if factor <= 1.0:
            continue
        for i in beat["range_idxs"]:
            edl.ranges[i].speed = factor
        saved = S * (1.0 - 1.0 / factor)
        gap -= saved
        info["beats_sped"].append(
            {"label": beat["label"], "factor": factor, "ranges": len(beat["range_idxs"]), "saved_s": round(saved, 1)}
        )

    edl.total_duration_s = _recompute_total(edl)
    # invariant: never exceed the configured cap
    assert all((r.speed or 1.0) <= cap + 1e-6 for r in edl.ranges), "speed cap violated"
    info["applied"] = bool(info["beats_sped"])
    info["duration_after_s"] = edl.total_duration_s
    info["ceiling_missed_s"] = round(max(0.0, edl.total_duration_s - ceiling), 1)
    return info
