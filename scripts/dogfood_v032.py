"""v0.3.2 dogfood driver: run the cut loop on a prepared run dir (transcript cached) and report the
over-ceiling trajectory, then optionally exercise the deterministic trim-to-fit backstop on the
chosen cut. Lighter than `eddy run` — proxy renders only, no final/studio-sound/shorts/package.

Usage: .venv/bin/python scripts/dogfood_v032.py <run_dir> [--trim]

The whole point: under v0.3 this source floored at iteration 3 (~19.6min over the 14-min ceiling)
because the plateau fired on flat edit-quality while duration was STILL dropping. v0.3.2's
feasibility-gated plateau should keep cutting past iter 3 toward the ceiling.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    run_dir = Path(sys.argv[1]).expanduser().resolve()
    do_trim = "--trim" in sys.argv

    from eddy.config import load_config
    from eddy.loop.controller import edit_loop
    from eddy.loop.receipts import Receipts
    from eddy.loop.state import RunState

    print(f"=== v0.3.2 dogfood: {run_dir.name} (trim_backstop={do_trim}) ===", flush=True)
    chosen = edit_loop(run_dir)
    s = RunState(run_dir)

    print("\n=== loop trajectory (feasibility-gated plateau) ===", flush=True)
    for a in s.data.get("attempts", []):
        print(f"  iter {a['iteration']:>2}: gates={a['gates_passed']!s:5} "
              f"over_ceiling_s={a.get('over_ceiling_s'):>7} quality={a.get('quality')}", flush=True)
    print(f"  iterations run: {len(s.data.get('attempts', []))} | chosen: {chosen.name} | phase: {s.data.get('phase')}",
          flush=True)

    # surface the v0.3.2 receipts of interest
    rl = run_dir / "receipts.jsonl"
    if rl.exists():
        for line in rl.read_text().splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") in ("protection_budget", "plateau_stop"):
                print(f"  receipt[{r['event']}]: " + json.dumps({k: v for k, v in r.items() if k not in ("event", "ts")}),
                      flush=True)

    from eddy.edit.schema import load_decisions, load_edl
    edl = load_edl(chosen / "edl.json")
    ceiling_s = load_config().loop.length_ceiling_minutes * 60
    print(f"\n  CHOSEN duration: {edl.total_duration_s:.0f}s ({edl.total_duration_s / 60:.1f}min) | "
          f"ceiling {ceiling_s:.0f}s ({ceiling_s / 60:.0f}min) | "
          f"over by {max(0.0, edl.total_duration_s - ceiling_s):.0f}s", flush=True)

    if do_trim:
        print("\n=== trim-to-fit backstop (enable_aggressive_trim=True) ===", flush=True)
        from eddy.loop.trim import trim_to_fit
        from eddy.providers.base import get_editorial_provider

        cfg = load_config()
        cfg.loop.enable_aggressive_trim = True
        receipts = Receipts(run_dir)
        provider = get_editorial_provider(cfg, receipts)
        decisions = load_decisions(chosen / "edit-decisions.json")
        sim = json.loads((chosen / "sim-report.json").read_text())
        info = trim_to_fit(edl, decisions, sim, run_dir, chosen, provider, receipts, cfg)
        print("  trim result: " + json.dumps({k: info[k] for k in (
            "applied", "adopted", "duration_before_s", "duration_after_s",
            "ceiling_missed_s", "revert_reason")}), flush=True)
        if info.get("beats_dropped"):
            print("  beats dropped: " + json.dumps(info["beats_dropped"]), flush=True)

    print("\n=== dogfood done ===", flush=True)


if __name__ == "__main__":
    main()
