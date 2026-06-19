"""v1.7: best-of-N self-consistency for the iteration-1 editorial draft.

The local 27B brain is non-deterministic — the SAME prompt produces wildly different cuts
(2.6 / 4.9 / 11.3 min on one source). A single draw is a coin flip. `best_of_n_decisions` samples N
independent `initial_decisions` drafts, compiles + simulates each (render-free, $0 beyond the N model
calls), and picks the winner by a DETERMINISTIC selector — the render-free *objective* half of
`quality_score`, then closest-to-ceiling feasibility band, then fewest blocks (more contiguous).

Why this is a STRONGER, STEADIER brain, not just a slower one: the selected draft is the max of N
draws under a fixed metric. max-of-N raises the floor (a bad single draw is discarded) AND shrinks the
spread of the SELECTED output (order statistics of the max concentrate as N grows). It converts the
model's variance from a liability into a selection advantage — exactly the lever the goal asks for.

Only iteration 1 is ensembled: it is the dominant variance source (the whole cut structure is chosen
here) and the cheapest place to spend extra draws. The revise/repair loop stays single-sample.
"""

from __future__ import annotations

from eddy.config import EddyConfig
from eddy.edit.compiler import CompileError, cut_transcript
from eddy.edit.cutplan import compile_with_repair, initial_decisions
from eddy.edit.schema import EditDecisions
from eddy.edit.simulate import simulate
from eddy.loop.receipts import Receipts
from eddy.qa.quality import quality_score
from eddy.transcribe.pack import phrases as load_phrases


def _selector_key(objective: float, over_ceiling_s: float, n_ranges: int) -> tuple:
    """Deterministic winner key (higher wins), feasibility-first, PRE-render (no gates/judge yet):
      1. feasibility band — closest to under-ceiling first (0 when under; more-over = more negative),
      2. fewest blocks (`-n_ranges`) — the more contiguous extract; directly serves the continuity goal,
      3. the model-proof `objective` score (quality.py, render-free) as the final tiebreak.

    v1.7.1: blocks rank ABOVE objective (was below). The v1.7 N=3 confirmation exposed the flaw — the
    `objective` half of quality_score is a near-constant, weak discriminator (8.1–9.1) that perversely
    REWARDS bloated keeps (more content -> higher hook/closure/pacing signals), so ranking it above
    block-count made the selector pick a 77-block draft over an 18-block one (confirm-d4). Contiguity is
    the goal-relevant axis; objective only breaks ties between similarly-tight drafts."""
    band = -round(over_ceiling_s / 120.0)
    return (band, -n_ranges, round(objective, 4))


def score_draft(run_dir, decisions: EditDecisions, provider, receipts: Receipts,
                cfg: EddyConfig, target_s: float, phrases: list[dict]):
    """Compile + simulate one draft and return (decisions, edl, sim, score, key). Render-free, $0.

    Uses the SAME `compile_with_repair` the loop uses, so a draft is scored exactly as it would
    render. `quality_score` is passed `judge={}` — its `objective` half never reads the judge, so the
    selector stays 100% deterministic (no LLM critic in the loop)."""
    decisions, edl = compile_with_repair(run_dir, decisions, provider, receipts, cfg)
    sim = simulate(edl, decisions, phrases, cfg, target_s)
    kept = cut_transcript(edl, phrases)
    qs = quality_score(sim, {}, kept, decisions, phrases, cfg)
    key = _selector_key(qs["objective"], qs["over_ceiling_s"], len(edl.ranges))
    return decisions, edl, sim, qs, key


def best_of_n_decisions(
    run_dir, provider, receipts: Receipts, target_s: float,
    retake_hints: list[dict], filler_hints: list[dict], beats: list[dict],
    cfg: EddyConfig, focus: str | None = None, focus_mode: str | None = None, n: int = 3,
) -> EditDecisions:
    """Sample N iteration-1 drafts; return the decisions of the best by the deterministic selector.

    Falls back to a single plain draft if every draft fails to compile, so the loop always proceeds.
    n<=1 degenerates to a single ordinary draft (no extra cost) — the off switch."""
    n = max(1, int(n))
    phrases = load_phrases(run_dir)
    best: tuple | None = None  # (key, draft_idx, decisions)
    n_ok = 0
    for i in range(n):
        draft = initial_decisions(
            run_dir, provider, receipts, target_s, retake_hints, filler_hints, beats, cfg,
            focus=focus, focus_mode=focus_mode,
        )
        try:
            draft, edl, _sim, qs, key = score_draft(run_dir, draft, provider, receipts, cfg, target_s, phrases)
        except CompileError as e:
            receipts.log("ensemble_draft_failed", draft=i, problems=getattr(e, "problems", [])[:5])
            continue
        n_ok += 1
        receipts.log(
            "ensemble_draft", draft=i, objective=qs["objective"], ranges=len(edl.ranges),
            over_ceiling_s=qs["over_ceiling_s"], dur_s=round(edl.total_duration_s, 1),
        )
        if best is None or key > best[0]:
            best = (key, i, draft)

    if best is None:
        receipts.log("ensemble_all_failed", n=n)
        return initial_decisions(
            run_dir, provider, receipts, target_s, retake_hints, filler_hints, beats, cfg,
            focus=focus, focus_mode=focus_mode,
        )
    receipts.log("ensemble_pick", draft=best[1], key=list(best[0]), n_ok=n_ok, n=n)
    return best[2]
