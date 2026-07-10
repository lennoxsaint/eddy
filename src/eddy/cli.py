"""Small JSON CLI around Eddy's public service boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import __version__
from .service import EddyService


def _service(runs_root: str | None) -> EddyService:
    root = Path(runs_root).expanduser() if runs_root else Path.home() / ".eddy" / "runs"
    return EddyService(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eddy", description="Proof-gated skill-first video editor")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--runs-root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    edit = sub.add_parser("edit")
    edit.add_argument("source")
    status = sub.add_parser("status")
    status.add_argument("job_id")
    cancel = sub.add_parser("cancel")
    cancel.add_argument("job_id")
    bundle = sub.add_parser("bundle")
    bundle.add_argument("job_id")
    bundle.add_argument("--output", default=None)
    sub.add_parser("sync-doctor")
    args = parser.parse_args(argv)
    service = _service(args.runs_root)
    actions: dict[str, Any] = {
        "edit": lambda: service.edit_start(args.source),
        "status": lambda: service.job_status(args.job_id),
        "cancel": lambda: service.cancel_job(args.job_id),
        "bundle": lambda: service.support_bundle(args.job_id, args.output),
        "sync-doctor": service.sync_doctor,
    }
    try:
        payload = actions[args.command]()
    except Exception as exc:  # noqa: BLE001 - CLI returns exact public blocker
        print(json.dumps({"status": "error", "blocker": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
