"""Small JSON CLI around Eddy's public service boundary."""

from __future__ import annotations

import argparse
import json
import sys
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
    edit.add_argument("--format", default="youtube")
    options = sub.add_parser("options")
    options.add_argument("source")
    options.add_argument("--format", default="youtube")
    packet = sub.add_parser("packet")
    packet.add_argument("job_id")
    submit = sub.add_parser("submit")
    submit.add_argument("job_id")
    submit.add_argument("plan", help="EditPlanV3 JSON path, or - for stdin")
    finalize = sub.add_parser("finalize")
    finalize.add_argument("job_id")
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
        "edit": lambda: service.edit_start(args.source, format=args.format),
        "options": lambda: service.edit_options(args.source, format=args.format),
        "packet": lambda: service.host_packet(args.job_id),
        "submit": lambda: service.host_submit(args.job_id, _read_plan(args.plan)),
        "finalize": lambda: service.finalize(args.job_id),
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


def _read_plan(value: str) -> dict[str, Any]:
    raw = sys.stdin.read() if value == "-" else Path(value).expanduser().read_text()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("edit_plan_must_be_json_object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
