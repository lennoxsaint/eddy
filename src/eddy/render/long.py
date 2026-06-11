"""Render the long edit (proxy or final) from a run's current/selected EDL."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.config import load_config
from eddy.edit.schema import load_edl
from eddy.loop.receipts import Receipts
from eddy.media.frames import boundary_contact_sheet
from eddy.render.segments import render_edl


def latest_iteration_dir(run_dir: Path) -> Path:
    iters = sorted((Path(run_dir) / "iterations").glob("[0-9]*"))
    if not iters:
        raise FileNotFoundError(f"no iterations in {run_dir} — run `eddy plan` first")
    return iters[-1]


def render_run(run_dir: Path, proxy: bool = False, iteration: int | None = None) -> Path:
    run_dir = Path(run_dir)
    cfg = load_config()
    receipts = Receipts(run_dir)

    iter_dir = (
        run_dir / "iterations" / f"{iteration:02d}" if iteration else latest_iteration_dir(run_dir)
    )
    edl = load_edl(iter_dir / "edl.json")

    if proxy:
        out = iter_dir / "proxy.mp4"
        render_edl(edl, out, run_dir, cfg.render, receipts=receipts, proxy=True)
        sheet = boundary_contact_sheet(out, edl, iter_dir / "contact-sheet.jpg", run_dir)
        receipts.log("contact_sheet", path=str(sheet))
    else:
        out = run_dir / "final" / "video.mp4"
        render_edl(edl, out, run_dir, cfg.render, receipts=receipts, proxy=False)
        (run_dir / "final" / "edl.json").write_text(json.dumps(edl.model_dump(), indent=1))
    print(out)
    return out
