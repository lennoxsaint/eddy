"""Render the long edit (proxy or final) from a run's current/selected EDL."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import load_config
from eddy.edit.schema import load_decisions, load_edl
from eddy.loop.receipts import Receipts
from eddy.media.frames import boundary_contact_sheet
from eddy.render.segments import render_edl


def latest_iteration_dir(run_dir: Path) -> Path:
    iters = sorted((Path(run_dir) / "iterations").glob("[0-9]*"))
    if not iters:
        raise FileNotFoundError(f"no iterations in {run_dir} — run `eddy plan` first")
    return iters[-1]


def render_run(run_dir: Path, proxy: bool = False, iteration: int | None = None) -> Path:
    run_dir = Path(run_dir).expanduser().resolve()
    cfg = load_config()
    receipts = Receipts(run_dir)

    iter_dir = (
        run_dir / "iterations" / f"{iteration:02d}" if iteration else latest_iteration_dir(run_dir)
    )
    edl = load_edl(iter_dir / "edl.json")
    decisions = None
    visual_insert_notes = []
    if (iter_dir / "edit-decisions.json").exists():
        decisions = load_decisions(iter_dir / "edit-decisions.json")
        visual_insert_notes = decisions.visual_insert_notes

    if proxy:
        out = iter_dir / "proxy.mp4"
        render_edl(
            edl, out, run_dir, cfg.render, receipts=receipts, proxy=True,
            visual_insert_notes=visual_insert_notes,
        )
        sheet = boundary_contact_sheet(out, edl, iter_dir / "contact-sheet.jpg", run_dir)
        receipts.log("contact_sheet", path=str(sheet))
    else:
        out = run_dir / "final" / "video.mp4"
        render_edl(
            edl, out, run_dir, cfg.render, receipts=receipts, proxy=False,
            visual_insert_notes=visual_insert_notes,
        )
        (run_dir / "final" / "edl.json").write_text(json.dumps(edl.model_dump(), indent=1))
        if cfg.audio.studio_sound:
            from eddy.render.audio import studio_sound

            audio_result = studio_sound(out, run_dir, cfg.audio, receipts=receipts)
            if not audio_result.get("quality_gate_pass", False):
                raise RuntimeError(audio_result.get("error") or "Studio Sound quality gate failed")
        if cfg.motion.mode.strip().lower() != "off":
            from eddy.render.motion import apply_first_60_motion

            motion_result = apply_first_60_motion(out, run_dir, cfg, receipts=receipts)
            if not motion_result.get("quality_gate_pass", False):
                raise RuntimeError(motion_result.get("error") or "First-60 motion quality gate failed")
        from eddy.qa.deterministic import run_deterministic, save as save_qa

        final_qa = run_deterministic(
            out,
            edl,
            run_dir,
            cfg,
            protected_count=len(decisions.protected_moments) if decisions else 0,
            check_loudness=cfg.audio.studio_sound,
            check_visual_blink=True,
        )
        save_qa(final_qa, run_dir / "final", name="qa-final.json")
        receipts.log("final_render", path=str(out), qa_pass=final_qa["pass"])
    print(out)
    return out
