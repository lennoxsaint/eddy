"""The agentic loop: iterate decisions -> compile -> simulate -> proxy -> judge -> gate
until done (or best attempt after max iterations), then final render + shorts + kit."""

from __future__ import annotations

import json
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
from eddy.loop.state import RunState
from eddy.media.frames import boundary_contact_sheet
from eddy.providers.base import get_provider
from eddy.qa.deterministic import run_deterministic
from eddy.qa.deterministic import save as save_qa
from eddy.qa.judge import run_judge
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
    if not sim["verdicts"]["duration_in_band"]:
        if sim["duration_s"] > sim["target_s"]:
            over = sim["duration_s"] - sim["target_s"]
            directive.append(
                {
                    "op": "drop_beat",
                    "reason": (
                        f"video is {over:.0f}s OVER target ({sim['duration_s']:.0f}s vs {sim['target_s']:.0f}s). "
                        f"Trims will not get there — remove roughly {over:.0f}s of content structurally: "
                        "cut the weakest beats entirely, collapse repeated explanations to their best telling, "
                        "and apply every RECOMMENDED and OPTIONAL tier opportunity. Keep hook, payoffs, CTA."
                    ),
                }
            )
        else:
            directive.append(
                {"op": "restore", "reason": f"video {sim['duration_s']:.0f}s under band — restore the weakest RECOMMENDED cuts"}
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
    provider = get_provider(cfg)
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
        receipts.log("target_clamped", requested_s=round(target_s), feasible_s=round(feasible_s), speech_s=round(speech_s))
        target_s = round(feasible_s * 0.9)

    decisions = None
    start_iter = 1
    directive: list[dict] = []
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
            elif directive:
                decisions = revise_decisions(run_dir, provider, receipts, decisions, directive, iteration)
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

        qa = run_deterministic(proxy, edl, run_dir, cfg, sim_report=sim)
        save_qa(qa, iter_dir)

        kept = cut_transcript(edl, phrases)
        judge = run_judge(provider, receipts, sim, decisions, edl, kept, cfg)
        (iter_dir / "judge.json").write_text(json.dumps(judge, indent=1))

        judge_ok = judge["weighted"] >= threshold or judge.get("advisory_only", False)
        gates_ok = qa["pass"]
        state.record_attempt(iteration, gates_ok, judge["weighted"], edl.total_duration_s - target_s)
        receipts.log(
            "gate", iteration=iteration, deterministic=gates_ok,
            judge_score=judge["weighted"], judge_unstable=judge.get("judge_unstable"),
            done=gates_ok and judge_ok,
        )

        if gates_ok and judge_ok:
            state.set_phase("loop_done")
            return iter_dir

        directive = _directive_from(qa, judge, sim)
        (iter_dir / "revision-directive.json").write_text(json.dumps(directive, indent=1))

    best = state.best()
    receipts.log("best_attempt", **best, shipped_with_failures=not best["gates_passed"])
    state.set_phase("loop_done_best_attempt")
    return run_dir / "iterations" / f"{best['iteration']:02d}"


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

    state.set_phase("final_render")
    edl = load_edl(chosen / "edl.json")
    final = run_dir / "final" / "video.mp4"
    render_edl(edl, final, run_dir, cfg.render, receipts=receipts, proxy=False)
    (run_dir / "final" / "edl.json").write_text(json.dumps(edl.model_dump(), indent=1))

    final_qa = run_deterministic(final, edl, run_dir, cfg)
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
