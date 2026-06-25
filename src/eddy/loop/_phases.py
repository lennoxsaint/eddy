"""The iterative edit phase: decisions -> compile -> simulate -> proxy -> judge -> gate,
branching from best with feasibility-gated plateau/budget stops, until a clean ship or best-effort."""

from __future__ import annotations

import json
import time
from pathlib import Path

from eddy.config import load_config
from eddy.cost import run_cost_summary
from eddy.edit.compiler import CompileError, cut_transcript
from eddy.edit.cutplan import (
    beat_map,
    compile_with_repair,
    initial_decisions,
    revise_decisions,
)
from eddy.edit.retakes import filler_candidates, retake_candidates
from eddy.edit.schema import load_decisions, save
from eddy.edit.simulate import save_report, simulate
from eddy.loop._diagnostics import (
    _budget_exhausted,
    _cost_cap_hit,
    _failure_signature,
    _loop_progress,
    _plateau_step,
    _record_model_pin,
)
from eddy.loop._directives import _directive_from
from eddy.loop.receipts import Receipts
from eddy.loop.state import RunState
from eddy.media.frames import boundary_contact_sheet
from eddy.providers.base import get_editorial_provider
from eddy.qa.deterministic import run_deterministic
from eddy.qa.deterministic import save as save_qa
from eddy.qa.judge import run_judge
from eddy.qa.quality import quality_score
from eddy.render.segments import render_edl
from eddy.runs import manifest
from eddy.transcribe.pack import phrases as load_phrases
from eddy.transcribe.whisper import words_flat


class EditLoopError(RuntimeError):
    """Raised when the loop cannot produce any compilable edit to ship."""


def edit_loop(run_dir: Path, target_minutes: float | None = None, resume: bool = False,
              ceiling_minutes: float | None = None, focus: str | None = None,
              focus_mode: str | None = None) -> Path:
    """Iterate to a gated EDL. Returns the chosen iteration dir."""
    run_dir = Path(run_dir)
    cfg = load_config()
    receipts = Receipts(run_dir)
    state = RunState(run_dir)
    provider = get_editorial_provider(cfg, receipts)  # beat map/decisions/revise/judge; mechanical stays local
    _record_model_pin(run_dir, cfg, receipts)  # reproducibility: pin the brain, warn on drift
    target_s = (target_minutes or cfg.loop.default_target_minutes) * 60
    # the user focus brief lives in the immutable manifest (set once at open_run); read it from there
    # so a --resume without --focus keeps the same brief. An explicit arg still wins on the first call.
    if focus is None or focus_mode is None:
        rs = manifest(run_dir).get("run_settings", {}) if (run_dir / "manifest.json").exists() else {}
        focus = focus if focus is not None else (rs.get("focus") or None)
        focus_mode = focus_mode if focus_mode is not None else (rs.get("focus_mode") or None)
    if focus:
        receipts.log("focus_edit", focus=focus[:300], mode=focus_mode or "steer")
    threshold = cfg.loop.judge_threshold

    words = words_flat(run_dir)
    phrases = load_phrases(run_dir)
    beats = beat_map(run_dir, provider, receipts)

    # a target above what the footage actually contains is unreachable — clamp to
    # the speakable content (speech + tightened-gap allowance) so the duration
    # band is honest and directives never demand restoring content that isn't there
    speech_s = sum(p["end"] - p["start"] for p in phrases)
    feasible_s = speech_s * 1.08  # tightened gaps remain between phrases
    if target_s > feasible_s * 0.95:
        # asking for more than the footage holds: clamp to 0.8x feasible so the loop
        # still demands real compression rather than settling for a loose all-content cut
        receipts.log("target_clamped", requested_s=round(target_s), feasible_s=round(feasible_s), speech_s=round(speech_s))
        target_s = round(feasible_s * 0.8)

    # format profiles (e.g. tutorials) can raise/disable the ceiling so the loop doesn't compress
    # step-by-step content; otherwise use the configured ceiling.
    ceiling_s = (ceiling_minutes if ceiling_minutes is not None else cfg.loop.length_ceiling_minutes) * 60
    loop_start = time.time()
    decisions = None
    start_iter = 1
    directive: list[dict] = []
    # v0.3: plateau state survives resume so a resumed run doesn't re-run the full cap
    prev_best_q = state.data.get("prev_best_q", -1.0)
    no_improve = state.data.get("no_improve", 0)
    # v0.3.2: min over_ceiling_s seen — the length convergence axis (1e9 sentinel = none yet)
    best_over = state.data.get("best_over", 1e9)
    over_ceiling_streak = state.data.get("over_ceiling_streak", 0)
    last_failure_signature = ""
    identical_failure_count = 0
    if resume and state.data["iteration"] >= 1:
        prev_dir = run_dir / "iterations" / f"{state.data['iteration']:02d}"
        if (prev_dir / "edit-decisions.json").exists():
            decisions = load_decisions(prev_dir / "edit-decisions.json")
            start_iter = state.data["iteration"] + 1
            directive_path = prev_dir / "revision-directive.json"
            if directive_path.exists():
                directive = json.loads(directive_path.read_text())
    for iteration in range(start_iter, cfg.loop.max_iterations + 1):
        # v0.4 runaway guard: after at least one attempt, stop if the cumulative wall-clock or
        # model-call budget is spent and ship best-effort. Model calls are counted from receipts
        # (model_call = decisions/beat-map, judge = critic) so the count survives --resume.
        if iteration > start_iter:
            events = receipts.read()
            model_calls = sum(1 for e in events if e.get("event") in ("model_call", "judge"))
            spend = run_cost_summary(events)["total_usd"]
            cap = cfg.loop.max_run_cost_usd
            if _budget_exhausted(time.time() - loop_start, model_calls, cfg.loop) or _cost_cap_hit(spend, cap):
                receipts.log(
                    "budget_exhausted", iteration=iteration,
                    elapsed_s=round(time.time() - loop_start, 1), model_calls=model_calls,
                    spend_usd=spend, cap_usd=cap,
                )
                break
        iter_dir = run_dir / "iterations" / f"{iteration:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        state.set_phase(f"iteration_{iteration}")

        try:
            if decisions is None:
                # v1.7: best-of-N self-consistency for the iteration-1 EXTRACT draft only. Gated on
                # ensemble_n>1 AND extract so normal/steer edits keep the single-draft path exactly.
                if cfg.loop.ensemble_n > 1 and focus_mode == "extract":
                    from eddy.edit.ensemble import best_of_n_decisions
                    decisions = best_of_n_decisions(
                        run_dir, provider, receipts, target_s,
                        retake_candidates(words), filler_candidates(words), beats, cfg,
                        focus=focus, focus_mode=focus_mode, n=cfg.loop.ensemble_n,
                    )
                else:
                    decisions = initial_decisions(
                        run_dir, provider, receipts, target_s,
                        retake_candidates(words), filler_candidates(words), beats, cfg,
                        focus=focus, focus_mode=focus_mode,
                    )
            else:
                # v0.3 branch-from-best: revise the BEST-so-far decisions using that best's
                # own directive, so a regression is never carried forward (autoresearch
                # keep-or-discard). Falls back to the in-memory pair when no best file exists.
                base, base_directive = decisions, directive
                if state.data["attempts"]:
                    bdir = run_dir / "iterations" / f"{state.best()['iteration']:02d}"
                    if (bdir / "edit-decisions.json").exists():
                        base = load_decisions(bdir / "edit-decisions.json")
                    if (bdir / "revision-directive.json").exists():
                        base_directive = json.loads((bdir / "revision-directive.json").read_text())
                if base_directive:
                    decisions = revise_decisions(run_dir, provider, receipts, base, base_directive, iteration)
            decisions.x_eddy.iteration = iteration
            decisions, edl = compile_with_repair(run_dir, decisions, provider, receipts, cfg)
        except CompileError as e:
            receipts.log("iteration_failed", iteration=iteration, problems=e.problems[:5])
            # over_ceiling_s=1e9 so a non-compilable attempt (no edl.json) sorts as maximally
            # INFEASIBLE in state.best() and can never out-rank a real over-ceiling cut. Without
            # this it records 0.0 -> ranks as perfectly feasible -> best() may pick it and the run
            # aborts on the missing edl.json, discarding good cuts. v0.3.2's keep-cutting posture
            # runs more iterations, so an intermittent compile failure is likelier to poison best().
            state.record_attempt(iteration, False, 0.0, target_s, over_ceiling_s=1e9)
            directive = [{"op": "restore", "defect": p, "reason": "compile failed"} for p in e.problems[:8]]
            continue

        save(decisions, iter_dir / "edit-decisions.json")
        save(edl, iter_dir / "edl.json")

        sim = simulate(edl, decisions, phrases, cfg, target_s)
        save_report(sim, iter_dir)

        proxy = iter_dir / "proxy.mp4"
        render_edl(edl, proxy, run_dir, cfg.render, receipts=receipts, proxy=True)
        try:
            boundary_contact_sheet(proxy, edl, iter_dir / "contact-sheet.jpg", run_dir)
        except Exception as e:
            receipts.log("contact_sheet_failed", error=str(e)[:200])

        qa = run_deterministic(
            proxy, edl, run_dir, cfg, sim_report=sim, protected_count=len(decisions.protected_moments)
        )
        save_qa(qa, iter_dir)

        kept = cut_transcript(edl, phrases)
        judge = run_judge(
            provider, receipts, sim, decisions, edl, kept, cfg,
            focus=decisions.x_eddy.focus, focus_mode=decisions.x_eddy.focus_mode,
        )
        (iter_dir / "judge.json").write_text(json.dumps(judge, indent=1))

        qual = quality_score(sim, judge, kept, decisions, phrases, cfg)
        (iter_dir / "quality.json").write_text(json.dumps(qual, indent=1))

        # v0.3 ship gate: deterministic gates green, a STABLE judge over threshold, and under
        # the length ceiling. The old advisory_only auto-pass is gone — an unstable judge
        # can never certify "done."
        gates_ok = qa["pass"]
        judge_ok = (not judge.get("judge_unstable")) and judge["weighted"] >= threshold
        under_ceiling = edl.total_duration_s <= ceiling_s
        over_ceiling_s = max(0.0, edl.total_duration_s - ceiling_s)
        # v0.3.2: consecutive rounds still over the ceiling drive directive escalation
        over_ceiling_streak = 0 if under_ceiling else over_ceiling_streak + 1
        state.data["over_ceiling_streak"] = over_ceiling_streak
        state.record_attempt(
            iteration, gates_ok, judge["weighted"], edl.total_duration_s - target_s,
            quality=qual["quality"], components=qual["components"],
            judge_unstable=bool(judge.get("judge_unstable")), over_ceiling_s=over_ceiling_s,
        )
        receipts.log(
            "gate", iteration=iteration, deterministic=gates_ok, quality=qual["quality"],
            judge_score=judge["weighted"], judge_unstable=judge.get("judge_unstable"),
            under_ceiling=under_ceiling, done=gates_ok and judge_ok and under_ceiling,
        )
        from eddy.ui import console as ui

        _prog = _loop_progress(
            iteration, cfg.loop.max_iterations, qual["quality"], judge["weighted"],
            over_ceiling_s, time.time() - loop_start,
        )
        ui.console().print(f"[eddy.accent]▸[/eddy.accent] [eddy.dim]{_prog}[/eddy.dim]")

        # clean-ship check runs BEFORE the plateau break so a passing iteration is never
        # thrown away by a plateau stop
        if gates_ok and judge_ok and under_ceiling:
            state.set_phase("loop_done")
            return iter_dir

        sig = _failure_signature(qa, judge, sim)
        identical_failure_count = identical_failure_count + 1 if sig == last_failure_signature else 1
        last_failure_signature = sig
        if cfg.loop.require_gate_pass and identical_failure_count >= cfg.loop.identical_failure_limit:
            receipts.log(
                "impossible_blocker",
                reason="identical_failure_signature",
                repeats=identical_failure_count,
                signature=json.loads(sig),
                iteration=iteration,
            )
            raise EditLoopError(
                "Eddy hit the same failing QA signature repeatedly after repair attempts. "
                "This is treated as an impossible blocker until the source media, dependency, or "
                "editorial instruction changes. See receipts event 'impossible_blocker'."
            )

        directive = _directive_from(qa, judge, sim, over_ceiling_streak, focus_mode=focus_mode)
        (iter_dir / "revision-directive.json").write_text(json.dumps(directive, indent=1))

        # v0.3.2 feasibility-gated plateau: stop only when NEITHER edit-quality NOR length is still
        # improving. The v0.3 plateau keyed solely on quality, but quality is deliberately blind to
        # length (a length term reward-hacked) — so the loop quit ~20min over the ceiling. Length is
        # now a SECOND convergence axis: while still materially over the ceiling AND each round cuts
        # meaningfully closer, keep going even if quality is flat. Once length progress stalls too
        # (the model can't cut more without quality collapse) or we're within tolerance, plateau and
        # ship best-effort. quality_score itself is untouched.
        cur_best_q = state.best().get("quality") or 0.0
        no_improve, prev_best_q, best_over, should_stop = _plateau_step(
            no_improve, prev_best_q, best_over, cur_best_q, over_ceiling_s, cfg.loop
        )
        state.set_plateau(no_improve, prev_best_q, best_over)
        if should_stop:
            if cfg.loop.require_gate_pass:
                receipts.log(
                    "plateau_ignored_require_gate_pass",
                    iteration=iteration,
                    best_quality=cur_best_q,
                    over_ceiling_s=round(over_ceiling_s, 1),
                    rounds=no_improve,
                )
                no_improve = 0
                state.set_plateau(no_improve, prev_best_q, best_over)
                continue
            receipts.log(
                "plateau_stop", iteration=iteration, best_quality=cur_best_q,
                over_ceiling_s=round(over_ceiling_s, 1), rounds=no_improve,
            )
            break

    best = state.best()
    chosen = run_dir / "iterations" / f"{best['iteration']:02d}"
    if not (chosen / "edl.json").exists():
        # Every iteration failed to compile a valid EDL — abort cleanly instead of
        # crashing later on a missing edl.json in final_render. The usual cause is the
        # editorial model emitting decisions the compiler rejects (e.g. cuts inside
        # declared protected_moments); a stronger editorial brain resolves it.
        receipts.log("loop_no_compilable_edl", iterations=cfg.loop.max_iterations)
        state.set_phase("loop_failed_no_edl")
        raise EditLoopError(
            f"No iteration produced a compilable EDL after {cfg.loop.max_iterations} attempts. "
            "The editorial model kept emitting decisions the compiler rejected (see receipts "
            "'iteration_failed' problems, e.g. cuts inside protected_moments). Set "
            "provider.editorial=claude_cli (or auto) for a stronger brain, then re-run."
        )
    if cfg.loop.require_gate_pass and not best["gates_passed"]:
        receipts.log("loop_failed_no_gate_passing_edit", **best)
        state.set_phase("loop_failed_no_gate_passing_edit")
        raise EditLoopError(
            f"No gate-passing edit after {cfg.loop.max_iterations} attempts. "
            "See receipts for the final failing QA signature and exact blocker."
        )
    receipts.log("best_attempt", **best, shipped_with_failures=not best["gates_passed"])
    state.set_phase("loop_done_best_attempt")
    return chosen
