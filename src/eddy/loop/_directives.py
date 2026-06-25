"""Directive synthesis: map deterministic QA + judge defects + length state into the typed
fix ops the editorial model consumes on the next revision pass."""

from __future__ import annotations


def _directive_from(qa: dict, judge: dict, sim: dict, over_ceiling_streak: int = 0,
                    focus_mode: str | None = None) -> list[dict]:
    """Typed fix ops: deterministic defects mapped by code, judge defects passed through.

    v0.3.2: when the cut is still over the ceiling, the drop_beat directive ESCALATES with
    over_ceiling_streak (consecutive rounds over) — naming more heavy beats and getting blunter —
    so a model that keeps under-cutting is pushed harder instead of receiving the identical nudge
    every round (which is what let the loop plateau ~20min over the ceiling).

    v1.6: an EXTRACT that is UNDER the ceiling has no length to win — compressing it only re-fragments
    a topical cut (restore/extend/tighten only, never drop_beat). But a v1.6 live run showed the local
    model is non-deterministic and can UNDER-cut badly (kept ~17min when ~3 was wanted); an over-ceiling
    extract MUST still be able to compress, or the loop grows it unboundedly and thrashes. So the
    continuity-only short-circuit fires ONLY while under the ceiling; an over-ceiling extract falls
    through to the normal compression path below."""
    directive: list[dict] = []
    for span in (sim.get("dead_air") or [])[:5]:
        directive.append(
            {"op": "tighten_gap", "out_s": span["after_out_s"], "quote": span["before"], "reason": f"{span['gap_s']}s dead air"}
        )
    if focus_mode == "extract" and sim.get("under_ceiling", True):
        for d in judge.get("defects", []):
            if d.get("fix_op") in ("restore", "extend_pad", "tighten_gap"):
                directive.append(
                    {"op": d["fix_op"], "out_s": d["out_s"], "quote": d["quote"], "reason": d.get("fix_note", d["type"])}
                )
        return directive[:10]
    # v0.3: length is a CEILING constraint, not a target band. Being short is fine (never
    # restore to pad). Over the ceiling → structural compression naming the heaviest beats.
    ceiling_s = sim.get("ceiling_s", sim.get("target_s", 0))
    if not sim.get("under_ceiling", True):
        over = sim["duration_s"] - ceiling_s
        n_heavy = 4 if over_ceiling_streak <= 1 else (6 if over_ceiling_streak == 2 else 8)
        heavy = sim.get("beat_density", [])[:n_heavy]
        heavy_hint = "; ".join(f"{b['label']} ({b['kept_s']:.0f}s @ {b['wpm']:.0f}wpm)" for b in heavy)
        reason = (
            f"video is {over:.0f}s OVER the {ceiling_s:.0f}s ceiling ({sim['duration_s']:.0f}s). "
            f"Trims will not get there — remove roughly {over:.0f}s of content structurally. "
            f"The longest beats are: {heavy_hint}. Attack these first: where a beat is the creator "
            "reading on-screen text/lists aloud, keep the intro line + the top 3 most important items and "
            "CUT THE REST (as ordinary cuts — no new ops); collapse repeated explanations to their best "
            "telling; cut the weakest beats entirely. Keep hook, payoffs, CTA."
        )
        if over_ceiling_streak >= 2:
            reason += (
                f" This is round {over_ceiling_streak} STILL over the ceiling — your last cut was not "
                "aggressive enough. Be bolder: cut the listed beats much harder."
            )
        if over_ceiling_streak >= 3:
            reason += (
                " The ceiling is firm. Cut the weakest 2-3 beats ENTIRELY and accept some roughness; "
                "the only content off-limits is a protected hook, payoff, or CTA."
            )
        directive.append({"op": "drop_beat", "reason": reason})
    else:
        # under ceiling: still nudge compression of information-light, fast-narrated runs so
        # the pacing quality signal can climb without a length violation
        light = [b for b in sim.get("beat_density", []) if b.get("wpm", 0) > 200 and b.get("kept_s", 0) > 45]
        if light:
            hint = "; ".join(f"{b['label']} ({b['kept_s']:.0f}s @ {b['wpm']:.0f}wpm)" for b in light[:3])
            directive.append(
                {"op": "drop_beat", "reason": (
                    f"These beats read fast and long (screen-narration): {hint}. Compress each to its intro "
                    "line + top 3 items as ordinary cuts; keep the insight, drop the read-through.")}
            )
    for d in judge.get("defects", []):
        if d["severity"] == "major" or len(directive) < 8:
            directive.append(
                {"op": d["fix_op"], "out_s": d["out_s"], "quote": d["quote"], "reason": d.get("fix_note", d["type"])}
            )
    return directive[:10]
