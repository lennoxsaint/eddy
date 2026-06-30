"""The end-to-end product flows: transcribe -> edit loop -> backstops -> ship panel -> final
render -> shorts -> kit (autonomous_run), and the shorts-only fast path (mine_shorts)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from eddy.config import EddyConfig, load_config
from eddy.cost import run_cost_summary
from eddy.edit.compiler import cut_transcript
from eddy.edit.schema import load_decisions, load_edl
from eddy.edit.simulate import simulate
from eddy.loop._diagnostics import _fmt_dur
from eddy.loop._phases import edit_loop
from eddy.loop.receipts import Receipts
from eddy.loop.speed import speed_to_fit
from eddy.loop.state import RunState
from eddy.loop.trim import trim_to_fit
from eddy.providers.base import get_editorial_provider
from eddy.qa.deterministic import run_deterministic
from eddy.qa.deterministic import save as save_qa
from eddy.qa.judge import run_ship_panel
from eddy.render.long import _failed_qa_gate_names
from eddy.render.segments import render_edl
from eddy.runs import assert_sources_decodable, manifest, open_run, verify_sources_unmutated
from eddy.transcribe.pack import phrases as load_phrases
from eddy.transcribe.whisper import transcribe_run, words_flat


def _warn_multispeaker(run_dir: Path, receipts: Receipts) -> None:
    """Non-blocking: surface a heuristic multi-speaker warning after transcription."""
    from eddy.edit.speakers import detect_multispeaker, multispeaker_warning

    try:
        det = detect_multispeaker(words_flat(run_dir))
    except Exception:
        return
    warning = multispeaker_warning(det)
    if warning:
        from eddy.ui import console as ui

        ui.warn(warning)
        receipts.log("multispeaker_warning", **det)


def _run_plan(cfg: EddyConfig, skip_shorts: bool, skip_package: bool) -> list[str]:
    """The ordered phase keys autonomous_run will actually execute for THIS run — the same conditionals
    that gate the set_phase() calls below, declared up front so the TUI shows an honest 'step k of N'
    (a 'just the video' run is ~5 stages, not the full 10). Keys are the major phases the TUI maps;
    the variable-length edit loop is the single 'editing' step."""
    plan = ["transcribe", "editing"]
    if cfg.loop.enable_aggressive_trim:
        plan.append("trim_to_fit")
    if cfg.loop.enable_speed_ramp:
        plan.append("speed_to_fit")
    if cfg.loop.ship_panel:
        plan.append("ship_panel")
    plan.append("final_render")
    if cfg.audio.studio_sound:
        plan.append("studio_sound")
    if cfg.motion.mode.strip().lower() != "off":
        plan.append("first_60_motion")
    if not skip_shorts:
        plan.append("shorts")
    if not skip_package:
        plan.append("package")
    plan.append("done")
    return plan


def autonomous_run(
    source: Path,
    target_minutes: float | None = None,
    slug: str | None = None,
    resume: bool = False,
    skip_shorts: bool = False,
    skip_package: bool = False,
    language: str | None = None,
    ceiling_minutes: float | None = None,
    focus: str | None = None,
    focus_mode: str | None = None,
) -> Path:
    """The product: footage in, launch kit out."""
    cfg = load_config()
    run_dir = open_run(source, slug=slug, resume=resume, focus=focus, focus_mode=focus_mode)
    assert_sources_decodable(manifest(run_dir)["sources"])  # fail loud on corrupt/unsupported input
    receipts = Receipts(run_dir)
    state = RunState(run_dir)
    run_t0 = time.time()
    from eddy.ui import console as ui

    if ui.color_enabled():
        ui.print_sprite("working", small=True)
    ui.console().print(ui.banner("starting"))  # neutral: the live stage is shown by the phase, not here
    ui.note(f"run: {run_dir}")

    state.set_plan(_run_plan(cfg, skip_shorts, skip_package))  # honest per-run step count for the TUI
    state.set_phase("transcribe")
    ui.note("transcribing (this can take a few minutes on a long source)…")
    transcribe_run(run_dir, language=language)
    _warn_multispeaker(run_dir, receipts)

    chosen = edit_loop(run_dir, target_minutes=target_minutes, resume=resume, ceiling_minutes=ceiling_minutes,
                       focus=focus, focus_mode=focus_mode)
    ui.note(f"chosen iteration: {chosen.name}")

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
                ui.note(f"trim-to-fit: {trim_info['duration_before_s']:.0f}s -> {trim_info['duration_after_s']:.0f}s "
                        f"({len(trim_info['beats_dropped'])} beats; ceiling miss {trim_info['ceiling_missed_s']:.0f}s)")
            else:
                ui.note(f"trim-to-fit reverted ({trim_info['revert_reason']}) — keeping pre-trim cut")

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
            ui.note(f"speed-to-fit: {speed_info['duration_before_s']:.0f}s -> {speed_info['duration_after_s']:.0f}s "
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
        sim = simulate(
            edl,
            chosen_decisions,
            load_phrases(run_dir),
            cfg,
            cached_sim.get("target_s", edl.total_duration_s),
            words=words_flat(run_dir),
        )
        kept = cut_transcript(edl, load_phrases(run_dir))
        try:
            panel = run_ship_panel(
                provider, receipts, sim, chosen_decisions, edl, kept, cfg,
                focus=chosen_decisions.x_eddy.focus, focus_mode=chosen_decisions.x_eddy.focus_mode,
            )
            (run_dir / "final").mkdir(parents=True, exist_ok=True)
            (run_dir / "final" / "ship-panel.json").write_text(json.dumps(panel, indent=1))
            if not panel["ships"]:
                ui.note(f"ship panel dissent ({panel['yes']}/{panel['of']} ship) — delivering best anyway")
        except Exception as e:
            receipts.log("ship_panel_failed", error=str(e)[:300])

    state.set_phase("final_render")
    final = run_dir / "final" / "video.mp4"
    render_edl(
        edl, final, run_dir, cfg.render, receipts=receipts, proxy=False,
        visual_insert_notes=chosen_decisions.visual_insert_notes,
    )
    (run_dir / "final" / "edl.json").write_text(json.dumps(edl.model_dump(), indent=1))

    # Studio Sound: full-track audio enhancement on the rendered output. This used to be non-fatal,
    # which allowed ffmpeg-only polish to masquerade as Studio Sound quality. vNext blocks when the
    # configured heavy speech backend is missing.
    if cfg.audio.studio_sound:
        state.set_phase("studio_sound")
        from eddy.render.audio import studio_sound

        audio_result = studio_sound(final, run_dir, cfg.audio, receipts=receipts)
        if not audio_result.get("quality_gate_pass", False):
            raise RuntimeError(audio_result.get("error") or "Studio Sound quality gate failed")

    if cfg.motion.mode.strip().lower() != "off":
        state.set_phase("first_60_motion")
        from eddy.render.motion import apply_first_60_motion

        motion_result = apply_first_60_motion(final, run_dir, cfg, receipts=receipts)
        if not motion_result.get("quality_gate_pass", False):
            raise RuntimeError(motion_result.get("error") or "First-60 motion quality gate failed")

    final_qa = run_deterministic(
        final, edl, run_dir, cfg, protected_count=len(chosen_decisions.protected_moments),
        check_loudness=cfg.audio.studio_sound,
        check_visual_blink=True,
    )
    save_qa(final_qa, run_dir / "final", name="qa-final.json")
    receipts.log("final_render", path=str(final), qa_pass=final_qa["pass"])
    if not final_qa.get("pass", False):
        failed = _failed_qa_gate_names(final_qa)
        receipts.log("final_render_blocked", path=str(final), failed_gates=failed)
        failed_text = ", ".join(failed) if failed else "unknown"
        raise RuntimeError(f"Final QA failed: {failed_text}")

    if not skip_shorts:
        state.set_phase("shorts")
        try:
            from eddy.render.shorts import render_shorts

            render_shorts(run_dir, iteration_dir=chosen)
        except Exception as e:
            receipts.log("shorts_failed", error=str(e)[:400])
            ui.warn(f"shorts failed (continuing): {e}")

    if not skip_package:
        state.set_phase("package")
        try:
            from eddy.package.launch_kit import package_run

            package_run(run_dir, iteration_dir=chosen)
        except Exception as e:
            receipts.log("package_failed", error=str(e)[:400])
            ui.warn(f"packaging failed (continuing): {e}")

    verify_sources_unmutated(run_dir)
    cost = run_cost_summary(receipts.read())
    receipts.log("run_cost", **cost)
    state.set_phase("done")
    cost_note = f" · editorial cost ${cost['total_usd']} ({cost['calls']} paid calls)" if cost["total_usd"] > 0 else " · $0 (local brain)"
    if ui.color_enabled():
        ui.print_sprite("success", small=True)
    ui.ok(f"done in {_fmt_dur(time.time() - run_t0)}{cost_note} · launch kit: {run_dir / 'final'}")
    return run_dir


def mine_shorts(
    source: Path,
    slug: str | None = None,
    resume: bool = False,
    language: str | None = None,
) -> Path:
    """Standalone `eddy shorts <source>`: transcribe -> ONE decision pass -> render shorts only.
    Skips the iterative judge/revise loop and the long-form render — for creators who only want
    vertical clips out of a source, fast and cheap. Source is never mutated."""
    from eddy.edit.cutplan import plan_run
    from eddy.render.shorts import render_shorts

    run_dir = open_run(source, slug=slug, resume=resume)
    assert_sources_decodable(manifest(run_dir)["sources"])  # fail loud on corrupt/unsupported input
    receipts = Receipts(run_dir)
    state = RunState(run_dir)
    run_t0 = time.time()
    from eddy.ui import console as ui

    if ui.color_enabled():
        ui.print_sprite("working", small=True)
    ui.console().print(ui.banner("mining shorts"))
    ui.note(f"run: {run_dir}")

    state.set_plan(["transcribe", "editing", "shorts", "done"])  # the shorts-only path is 4 stages
    state.set_phase("transcribe")
    ui.note("transcribing (this can take a few minutes on a long source)…")
    transcribe_run(run_dir, language=language)
    _warn_multispeaker(run_dir, receipts)

    state.set_phase("plan")
    ui.note("finding short-worthy moments…")
    iter_dir = plan_run(run_dir)  # iteration-1 decisions incl. shorts_candidates

    state.set_phase("shorts")
    shorts = render_shorts(run_dir, iteration_dir=iter_dir)

    verify_sources_unmutated(run_dir)
    cost = run_cost_summary(receipts.read())
    receipts.log("run_cost", **cost)
    state.set_phase("done")
    cost_note = f" · editorial cost ${cost['total_usd']}" if cost["total_usd"] > 0 else " · $0 (local brain)"
    if ui.color_enabled():
        ui.print_sprite("success", small=True)
    ui.ok(f"{len(shorts)} short(s) in {_fmt_dur(time.time() - run_t0)}{cost_note} · {run_dir / 'final' / 'shorts'}")
    return run_dir
