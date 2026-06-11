"""Standalone `eddy qa`: run deterministic QA (+judge if artifacts exist) on an iteration."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import load_config
from eddy.edit.compiler import cut_transcript
from eddy.edit.schema import load_decisions, load_edl
from eddy.loop.receipts import Receipts
from eddy.providers.base import get_provider
from eddy.qa.deterministic import run_deterministic, save
from eddy.qa.judge import run_judge
from eddy.render.long import latest_iteration_dir
from eddy.transcribe.pack import phrases as load_phrases


def qa_run(run_dir: Path, iteration: int | None = None) -> dict:
    run_dir = Path(run_dir)
    cfg = load_config()
    iter_dir = (
        run_dir / "iterations" / f"{iteration:02d}" if iteration else latest_iteration_dir(run_dir)
    )
    edl = load_edl(iter_dir / "edl.json")
    sim = json.loads((iter_dir / "sim-report.json").read_text()) if (iter_dir / "sim-report.json").exists() else None

    video = iter_dir / "proxy.mp4"
    if not video.exists():
        video = run_dir / "final" / "video.mp4"
    result: dict = {}
    if video.exists():
        result["deterministic"] = run_deterministic(video, edl, run_dir, cfg, sim_report=sim)
        save(result["deterministic"], iter_dir)

    if sim is not None and (iter_dir / "edit-decisions.json").exists():
        decisions = load_decisions(iter_dir / "edit-decisions.json")
        kept = cut_transcript(edl, load_phrases(run_dir))
        judge = run_judge(get_provider(cfg), Receipts(run_dir), sim, decisions, edl, kept, cfg)
        (iter_dir / "judge.json").write_text(json.dumps(judge, indent=1))
        result["judge"] = {"weighted": judge["weighted"], "defects": len(judge["defects"])}

    print(json.dumps({k: (v if k != "deterministic" else v["pass"]) for k, v in result.items()}, indent=1, default=str))
    return result
