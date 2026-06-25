"""Leaf diagnostic helpers for the agentic loop: plateau/budget/cost gating, failure
signatures, duration formatting, progress lines, and editorial-model identity/pinning."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.providers.base import _editorial_available


def _made_progress(cur_best_q: float, prev_best_q: float, over_ceiling_s: float, best_over: float, loop) -> bool:
    """v0.3.2 feasibility-gated plateau: the loop made progress this round if EITHER edit quality
    improved OR the cut got materially closer to the ceiling while still over it. Length is the
    second convergence axis — it gates the plateau but is never folded into the quality score (a
    length term reward-hacked in v0.3). Returns True to reset the no-improve counter."""
    q_improved = cur_best_q > prev_best_q + 1e-6
    len_improved = (
        over_ceiling_s > loop.ceiling_tolerance_s
        and over_ceiling_s < best_over - loop.min_length_progress_s
    )
    return q_improved or len_improved


def _plateau_step(no_improve: int, prev_best_q: float, best_over: float, cur_best_q: float,
                  over_ceiling_s: float, loop) -> tuple[int, float, float, bool]:
    """One feasibility-gated plateau step. Returns (no_improve, prev_best_q, best_over, should_stop).

    ORDER IS LOAD-BEARING: progress is judged against the PRE-update best_over (so this round's own
    cut counts as length progress, and on iteration 1 the 1e9 best_over sentinel makes the first
    over-ceiling cut count), THEN best_over absorbs this round. Moving the best_over update before
    the _made_progress call silently reintroduces the v0.3 quality-only plateau (the ~20min-over
    floor). Extracted so this order is unit-tested, not just the helper."""
    progressed = _made_progress(cur_best_q, prev_best_q, over_ceiling_s, best_over, loop)
    no_improve = 0 if progressed else no_improve + 1
    prev_best_q = max(prev_best_q, cur_best_q)
    best_over = min(best_over, over_ceiling_s)
    return no_improve, prev_best_q, best_over, no_improve >= loop.plateau_rounds


def _budget_exhausted(elapsed_s: float, model_calls: int, loop) -> bool:
    """v0.4 runaway guard: True once the cumulative wall-clock OR model-call budget is spent, so the
    loop stops and ships best-effort instead of running unbounded time/cost. max_model_calls_per_iteration
    was dead config; this enforces a real cumulative ceiling. Checked at the iteration head AFTER at
    least one attempt, so a run always produces a best-attempt."""
    return elapsed_s > loop.max_wall_clock_minutes * 60 or model_calls >= loop.max_total_model_calls


def _cost_cap_hit(spend_usd: float, cap_usd: float) -> bool:
    """v0.7 spend guard: True once cumulative paid-API spend reaches a positive cap (0 = unlimited).
    Checked at the iteration head (iter 2+), so the cap can overshoot by ~one iteration."""
    return cap_usd > 0 and spend_usd >= cap_usd


def _failure_signature(qa: dict, judge: dict, sim: dict) -> str:
    """Stable-ish signature for repeated no-progress failures."""
    failed_gates = sorted(g.get("gate", "unknown") for g in qa.get("gates", []) if not g.get("pass"))
    judge_defects = sorted((d.get("type") or d.get("fix_op") or "defect") for d in judge.get("defects", [])[:5])
    length_state = "under" if sim.get("under_ceiling", True) else "over"
    return json.dumps({"gates": failed_gates, "judge": judge_defects, "length": length_state}, sort_keys=True)


def _fmt_dur(s: float) -> str:
    s = int(max(0, s))
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def _loop_progress(iteration: int, max_iter: int, quality: float, judge: float, over_s: float, elapsed_s: float) -> str:
    """A one-line, human-readable progress + rough ETA for each loop iteration, so a multi-minute
    run never looks frozen. ETA extrapolates from the average iteration time so far."""
    eta = ""
    if iteration > 0:
        remaining = (elapsed_s / iteration) * max(0, max_iter - iteration)
        if remaining > 0:
            eta = f" · ~{_fmt_dur(remaining)} left (max)"
    over = f" · {_fmt_dur(over_s)} over ceiling" if over_s > 0 else " · under ceiling"
    return f"cut {iteration}/{max_iter} · q{quality:.2f} judge{judge:.1f}{over} · {_fmt_dur(elapsed_s)} in{eta}"


def _editorial_model_id(cfg) -> dict:
    """The resolved editorial brain identity (provider + model string) for reproducibility."""
    setting = cfg.provider.editorial
    if setting == "auto":
        chosen = _editorial_available(cfg) or cfg.provider.active
    elif setting == "local":
        chosen = cfg.provider.active
    else:
        chosen = setting
    model = {
        "ollama": cfg.provider.ollama.model,
        "anthropic": cfg.provider.anthropic.model,
        "openai": cfg.provider.openai.model,
        "claude_cli": cfg.provider.claude_cli.model,
        "codex_cli": cfg.provider.codex_cli.model,
    }.get(chosen, "")
    return {"provider": chosen, "model": model}


def _record_model_pin(run_dir: Path, cfg, receipts) -> None:
    """Record which editorial brain produced this run, and warn on drift. A cloud model can't be
    frozen by digest (the golden suite pins local qwen instead), but recording provider+model and
    flagging when a resumed/re-run uses a DIFFERENT brain than earlier iterations is the honest
    reproducibility signal — 'it got worse on re-run' is usually a silent model change."""
    pin = _editorial_model_id(cfg)
    path = run_dir / "model-pin.json"
    if path.exists():
        try:
            prior = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            prior = None
        if prior is not None and prior != pin:
            receipts.log("model_drift", prior=prior, current=pin)
        return
    from eddy.atomicio import atomic_write_text

    atomic_write_text(path, json.dumps(pin, indent=1))
    receipts.log("model_pin", **pin)
