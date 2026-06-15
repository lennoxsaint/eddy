"""The agentic loop: iterate decisions -> compile -> simulate -> proxy -> judge -> gate
until done (or best attempt after max iterations), then final render + shorts + kit."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import load_config
from eddy.edit.compiler import CompileError, cut_transcript


class EditLoopError(RuntimeError):
    """Raised when the loop cannot produce any compilable edit to ship."""
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
from eddy.media.frames import boundary_contact_sheet
from eddy.providers.base import get_editorial_provider
from eddy.qa.deterministic import run_deterministic
from eddy.qa.deterministic import save as save_qa
from eddy.qa.judge import run_judge, run_ship_panel
from eddy.qa.quality import quality_score
from eddy.render.segments import render_edl
from eddy.runs import open_run, verify_sources_unmutated
from eddy.transcribe.pack import phrases as load_phrases
from eddy.transcribe.whisper import transcribe_run, words_flat


def _directive_from(qa: dict, judge: dict, sim: dict) -> list[dict]:
    """Typed fix ops: deterministic defects mapped by code, judge defects passed through."""
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
        heavy = sim.get("beat_density", [])[:4]
        heavy_hint = "; ".join(f"{b['label']} ({b['kept_s']:.0f}s @ {b['wpm']:.0f}wpm)" for b in heavy)
        directive.append(
            {
                "op": "drop_beat",
                "reason": (
                    f"video is {over:.0f}s OVER the {ceiling_s:.0f}s ceiling ({sim['duration_s']:.0f}s). "
                    f"Trims will not get there — remove roughly {over:.0f}s of content structurally. "
                    f"The longest beats are: {heavy_hint}. Attack these first: where a beat is the creator "
                    "reading on-screen text/lists aloud, keep the intro line + the top 3 most important items and "
                    "CUT THE REST (as ordinary cuts — no new ops); collapse repeated explanations to their best "
                    "telling; cut the weakest beats entirely. Keep hook, payoffs, CTA."
                ),
            }
        )
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
    decisions = None
    start_iter = 1
    directive: list[dict] = []
    # v0.3: plateau state survives resume so a resumed run doesn't re-run the full cap
    prev_best_q = state.data.get("prev_best_q", -1.0)
    no_improve = state.data.get("no_improve", 0)
    if resume and state.data["iteration"] >= 1:
        prev_dir = run_dir / "iterations" / f"{state.data['iteration']:02d}"
        if (prev_dir / "edit-decisions.json").exists():
            decisions = load_decisions(prev_dir / "edit-decisions.json")
            start_iter = state.data["iteration"] + 1
            directive_path = prev_dir / "revision-directive.json"
            if directive_path.exists():
                directive = json.loads(directive_path.read_text())
    for iteration in range(start_iter, cfg.loop.max_iterations + 1):
        iter_dir = run_dir / "iterations" / f"{iteration:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        state.set_phase(f"iteration_{iteration}")

        try:
            if decisions is None:
                decisions = initial_decisions(
                    run_dir, provider, receipts, target_s,
                    retake_candidates(words), filler_candidates(words), beats,
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
            state.record_attempt(iteration, False, 0.0, target_s)
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

        # clean-ship check runs BEFORE the plateau break so a passing iteration is never
        # thrown away by a plateau stop
        if gates_ok and judge_ok and under_ceiling:
            state.set_phase("loop_done")
            return iter_dir

        directive = _directive_from(qa, judge, sim)
        (iter_dir / "revision-directive.json").write_text(json.dumps(directive, indent=1))

        # v0.3 plateau: stop when best quality hasn't improved for plateau_rounds rounds
        cur_best_q = state.best().get("quality") or 0.0
        if cur_best_q > prev_best_q + 1e-6:
            no_improve, prev_best_q = 0, cur_best_q
        else:
            no_improve += 1
        state.set_plateau(no_improve, prev_best_q)
        if no_improve >= cfg.loop.plateau_rounds:
            receipts.log("plateau_stop", iteration=iteration, best_quality=cur_best_q, rounds=no_improve)
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
) -> Path:
    """The product: footage in, launch kit out."""
    cfg = load_config()
    run_dir = open_run(source, slug=slug, resume=resume)
    receipts = Receipts(run_dir)
    state = RunState(run_dir)
    print(f"run: {run_dir}")

    state.set_phase("transcribe")
    transcribe_run(run_dir)

    chosen = edit_loop(run_dir, target_minutes=target_minutes, resume=resume)
    print(f"chosen iteration: {chosen.name}")

    # edit_loop used its own RunState and wrote the attempts/best_iter to disk. Reload here so
    # this function's later set_phase() saves don't clobber that record with stale empty data
    # (would wipe the state.json audit trail and break --resume of a finished run).
    state = RunState(run_dir)

    edl = load_edl(chosen / "edl.json")
    chosen_decisions = load_decisions(chosen / "edit-decisions.json")

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
        sim = json.loads((chosen / "sim-report.json").read_text())
        sim["duration_s"] = edl.total_duration_s  # honest: panel judges the sped, shipped duration
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
    print(f"launch kit: {run_dir / 'final'}")
    return run_dir
