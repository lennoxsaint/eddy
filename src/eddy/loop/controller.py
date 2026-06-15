"""The agentic loop: iterate decisions -> compile -> simulate -> proxy -> judge -> gate
until done (or best attempt after max iterations), then final render + shorts + kit."""

from __future__ import annotations

import json
import time
from pathlib import Path

from eddy.config import load_config
from eddy.edit.compiler import CompileError, cut_transcript
from eddy.edit.cutplan import (
    beat_map,
    compile_with_repair,
    initial_decisions,
    revise_decisions,
)
from eddy.edit.retakes import filler_candidates, retake_candidates
from eddy.edit.schema import load_decisions, load_edl, save
from eddy.edit.simulate import save_report, simulate
from eddy.loop.receipts import Receipts
from eddy.loop.speed import speed_to_fit
from eddy.loop.state import RunState
from eddy.loop.trim import trim_to_fit
from eddy.media.frames import boundary_contact_sheet
from eddy.providers.base import _editorial_available, get_editorial_provider
from eddy.qa.deterministic import run_deterministic
from eddy.qa.deterministic import save as save_qa
from eddy.qa.judge import run_judge, run_ship_panel
from eddy.qa.quality import quality_score
from eddy.render.segments import render_edl
from eddy.runs import assert_sources_decodable, manifest, open_run, verify_sources_unmutated
from eddy.transcribe.pack import phrases as load_phrases
from eddy.transcribe.whisper import transcribe_run, words_flat


class EditLoopError(RuntimeError):
    """Raised when the loop cannot produce any compilable edit to ship."""


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
    return f"[eddy] cut {iteration}/{max_iter} · q{quality:.2f} judge{judge:.1f}{over} · {_fmt_dur(elapsed_s)} in{eta}"


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


def _directive_from(qa: dict, judge: dict, sim: dict, over_ceiling_streak: int = 0) -> list[dict]:
    """Typed fix ops: deterministic defects mapped by code, judge defects passed through.

    v0.3.2: when the cut is still over the ceiling, the drop_beat directive ESCALATES with
    over_ceiling_streak (consecutive rounds over) — naming more heavy beats and getting blunter —
    so a model that keeps under-cutting is pushed harder instead of receiving the identical nudge
    every round (which is what let the loop plateau ~20min over the ceiling)."""
    directive: list[dict] = []
    for span in (sim.get("dead_air") or [])[:5]:
        directive.append(
            {"op": "tighten_gap", "out_s": span["after_out_s"], "quote": span["before"], "reason": f"{span['gap_s']}s dead air"}
        )
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


def edit_loop(run_dir: Path, target_minutes: float | None = None, resume: bool = False) -> Path:
    """Iterate to a gated EDL. Returns the chosen iteration dir."""
    run_dir = Path(run_dir)
    cfg = load_config()
    receipts = Receipts(run_dir)
    state = RunState(run_dir)
    provider = get_editorial_provider(cfg, receipts)  # beat map/decisions/revise/judge; mechanical stays local
    _record_model_pin(run_dir, cfg, receipts)  # reproducibility: pin the brain, warn on drift
    target_s = (target_minutes or cfg.loop.default_target_minutes) * 60
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

    ceiling_s = cfg.loop.length_ceiling_minutes * 60
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
            model_calls = sum(1 for e in receipts.read() if e.get("event") in ("model_call", "judge"))
            if _budget_exhausted(time.time() - loop_start, model_calls, cfg.loop):
                receipts.log(
                    "budget_exhausted", iteration=iteration,
                    elapsed_s=round(time.time() - loop_start, 1), model_calls=model_calls,
                )
                break
        iter_dir = run_dir / "iterations" / f"{iteration:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        state.set_phase(f"iteration_{iteration}")

        try:
            if decisions is None:
                decisions = initial_decisions(
                    run_dir, provider, receipts, target_s,
                    retake_candidates(words), filler_candidates(words), beats, cfg,
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
        judge = run_judge(provider, receipts, sim, decisions, edl, kept, cfg)
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
        print(_loop_progress(
            iteration, cfg.loop.max_iterations, qual["quality"], judge["weighted"],
            over_ceiling_s, time.time() - loop_start,
        ))

        # clean-ship check runs BEFORE the plateau break so a passing iteration is never
        # thrown away by a plateau stop
        if gates_ok and judge_ok and under_ceiling:
            state.set_phase("loop_done")
            return iter_dir

        directive = _directive_from(qa, judge, sim, over_ceiling_streak)
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
    receipts.log("best_attempt", **best, shipped_with_failures=not best["gates_passed"])
    state.set_phase("loop_done_best_attempt")
    return chosen


def autonomous_run(
    source: Path,
    target_minutes: float | None = None,
    slug: str | None = None,
    resume: bool = False,
    skip_shorts: bool = False,
    skip_package: bool = False,
    language: str | None = None,
) -> Path:
    """The product: footage in, launch kit out."""
    cfg = load_config()
    run_dir = open_run(source, slug=slug, resume=resume)
    assert_sources_decodable(manifest(run_dir)["sources"])  # fail loud on corrupt/unsupported input
    receipts = Receipts(run_dir)
    state = RunState(run_dir)
    run_t0 = time.time()
    print(f"run: {run_dir}")

    state.set_phase("transcribe")
    print("[eddy] transcribing (this can take a few minutes on a long source)…")
    transcribe_run(run_dir, language=language)

    chosen = edit_loop(run_dir, target_minutes=target_minutes, resume=resume)
    print(f"chosen iteration: {chosen.name}")

    # edit_loop used its own RunState and wrote the attempts/best_iter to disk. Reload here so
    # this function's later set_phase() saves don't clobber that record with stale empty data
    # (would wipe the state.json audit trail and break --resume of a finished run).
    state = RunState(run_dir)

    edl = load_edl(chosen / "edl.json")
    chosen_decisions = load_decisions(chosen / "edit-decisions.json")

    # v0.3.2 trim-to-fit: deterministic whole-beat CUTTING backstop for a residual gap the
    # model-driven loop couldn't close. Runs BEFORE speed-to-fit (exhaust cutting before speeding —
    # removing dead-weight beats beats rushing kept content) and re-judges its own trim, reverting
    # wholesale if it regressed. Off unless enable_aggressive_trim. Mutates edl in place on adopt.
    if cfg.loop.enable_aggressive_trim and (chosen / "sim-report.json").exists():
        state.set_phase("trim_to_fit")
        provider = get_editorial_provider(cfg, receipts)
        sim_for_trim = json.loads((chosen / "sim-report.json").read_text())
        trim_info = trim_to_fit(edl, chosen_decisions, sim_for_trim, run_dir, chosen, provider, receipts, cfg)
        if trim_info["applied"]:
            (run_dir / "final").mkdir(parents=True, exist_ok=True)
            (run_dir / "final" / "trim-to-fit.json").write_text(json.dumps(trim_info, indent=1))
            if trim_info["adopted"]:
                print(f"trim-to-fit: {trim_info['duration_before_s']:.0f}s -> {trim_info['duration_after_s']:.0f}s "
                      f"({len(trim_info['beats_dropped'])} beats; ceiling miss {trim_info['ceiling_missed_s']:.0f}s)")
            else:
                print(f"trim-to-fit reverted ({trim_info['revert_reason']}) — keeping pre-trim cut")

    # v0.3.1 speed-to-fit: deterministically time-compress the heaviest slow, non-protected beats
    # to close any residual gap to the length ceiling that cutting alone couldn't (off unless
    # enable_speed_ramp). Runs ONCE here, before the ship panel + final render, so the panel and
    # every downstream artifact (kept transcript, chapters, QA) reflect the actually-shipped cut.
    if cfg.loop.enable_speed_ramp and (chosen / "sim-report.json").exists():
        state.set_phase("speed_to_fit")
        sim_for_speed = json.loads((chosen / "sim-report.json").read_text())
        speed_info = speed_to_fit(edl, chosen_decisions, sim_for_speed.get("beat_density", []), cfg)
        receipts.log("speed_to_fit", applied=speed_info["applied"],
                     over_before_s=speed_info["over_before_s"], ceiling_missed_s=speed_info["ceiling_missed_s"],
                     duration_before_s=speed_info["duration_before_s"], duration_after_s=speed_info["duration_after_s"])
        if speed_info["applied"]:
            print(f"speed-to-fit: {speed_info['duration_before_s']:.0f}s -> {speed_info['duration_after_s']:.0f}s "
                  f"({len(speed_info['beats_sped'])} beats; ceiling miss {speed_info['ceiling_missed_s']:.0f}s)")
            (run_dir / "final").mkdir(parents=True, exist_ok=True)
            (run_dir / "final" / "speed-to-fit.json").write_text(json.dumps(speed_info, indent=1))

    # v0.3 final-ship panel: 3 independent lenses vote on the chosen best (once). Advisory —
    # records dissent to final/ship-panel.json but never blocks delivery.
    if cfg.loop.ship_panel and (chosen / "sim-report.json").exists():
        state.set_phase("ship_panel")
        provider = get_editorial_provider(cfg, receipts)
        # v0.3.2: re-simulate the FINAL edl so the panel judges the actually-shipped boundary cards.
        # trim-to-fit removes whole beats (new splices) and speed-to-fit changes durations, so the
        # cached pre-backstop sim-report would feed the panel stale evidence. No-op cost when neither
        # backstop ran (re-simulate is deterministic, no model calls).
        cached_sim = json.loads((chosen / "sim-report.json").read_text())
        sim = simulate(edl, chosen_decisions, load_phrases(run_dir), cfg, cached_sim.get("target_s", edl.total_duration_s))
        kept = cut_transcript(edl, load_phrases(run_dir))
        try:
            panel = run_ship_panel(provider, receipts, sim, chosen_decisions, edl, kept, cfg)
            (run_dir / "final").mkdir(parents=True, exist_ok=True)
            (run_dir / "final" / "ship-panel.json").write_text(json.dumps(panel, indent=1))
            if not panel["ships"]:
                print(f"ship panel dissent ({panel['yes']}/{panel['of']} ship) — delivering best anyway")
        except Exception as e:
            receipts.log("ship_panel_failed", error=str(e)[:300])

    state.set_phase("final_render")
    final = run_dir / "final" / "video.mp4"
    render_edl(edl, final, run_dir, cfg.render, receipts=receipts, proxy=False)
    (run_dir / "final" / "edl.json").write_text(json.dumps(edl.model_dump(), indent=1))

    # Studio Sound: full-track audio enhancement on the rendered output (non-fatal)
    if cfg.audio.studio_sound:
        state.set_phase("studio_sound")
        from eddy.render.audio import studio_sound

        studio_sound(final, run_dir, cfg.audio, receipts=receipts)

    final_qa = run_deterministic(
        final, edl, run_dir, cfg, protected_count=len(chosen_decisions.protected_moments),
        check_loudness=cfg.audio.studio_sound,
    )
    save_qa(final_qa, run_dir / "final", name="qa-final.json")
    receipts.log("final_render", path=str(final), qa_pass=final_qa["pass"])

    if not skip_shorts:
        state.set_phase("shorts")
        try:
            from eddy.render.shorts import render_shorts

            render_shorts(run_dir, iteration_dir=chosen)
        except Exception as e:
            receipts.log("shorts_failed", error=str(e)[:400])
            print(f"shorts failed (continuing): {e}")

    if not skip_package:
        state.set_phase("package")
        try:
            from eddy.package.launch_kit import package_run

            package_run(run_dir, iteration_dir=chosen)
        except Exception as e:
            receipts.log("package_failed", error=str(e)[:400])
            print(f"packaging failed (continuing): {e}")

    verify_sources_unmutated(run_dir)
    state.set_phase("done")
    print(f"[eddy] done in {_fmt_dur(time.time() - run_t0)} · launch kit: {run_dir / 'final'}")
    return run_dir
