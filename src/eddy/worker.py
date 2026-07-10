"""Detached worker entry point for long preflight and finalization stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import PipelineRunner
from .runtime import JobManager, JobState


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "finalize"))
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--canonical-root", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)
    manager = JobManager(Path(args.runs_root))
    runner = PipelineRunner(root=Path(args.canonical_root), manager=manager)
    try:
        if args.action == "prepare":
            runner.prepare(args.job_id)
        else:
            runner.finalize(args.job_id)
    except Exception as exc:  # noqa: BLE001 - detached worker must persist an exact blocker
        job = manager.load(args.job_id)
        if job.state not in {JobState.BLOCKED, JobState.CANCELLED, JobState.COMPLETED}:
            manager.block(args.job_id, f"worker_failed:{exc}")
            state_path = job.run_dir / "worker-error.json"
            state_path.write_text(json.dumps({"blocker": str(exc), "action": args.action}, indent=2) + "\n")
        elif job.state is JobState.CANCELLED:
            manager.quarantine_attempts(args.job_id)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
