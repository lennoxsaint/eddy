#!/usr/bin/env python3
"""Audit one source-mapped timeline manifest and emit a deterministic repair plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from eddy.cut_boundaries import audit_timeline, boundary_review_commands


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    parser.add_argument("--media")
    parser.add_argument("--review-dir")
    args = parser.parse_args()
    source = Path(args.manifest).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    payload = json.loads(source.read_text())
    _validate_protected_evidence(payload, source.parent)
    result = audit_timeline(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if bool(args.media) != bool(args.review_dir):
        parser.error("--media and --review-dir must be supplied together")
    if args.media and args.review_dir:
        media = Path(args.media).expanduser().resolve()
        review_dir = Path(args.review_dir).expanduser().resolve()
        review_dir.mkdir(parents=True, exist_ok=True)
        commands, relative_outputs = boundary_review_commands(
            media,
            result,
            review_dir,
        )
        for command in commands:
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(command, check=True)
        receipt = {
            "schema_version": "eddy-cut-boundary-review-v1",
            "decoder_policy": "fps_mode_passthrough",
            "frame_window_each_side": 8,
            "playback_speed": 0.25,
            "artifacts": [
                {
                    "ref": relative,
                    "sha256": hashlib.sha256(
                        (review_dir / relative).read_bytes()
                    ).hexdigest(),
                }
                for relative in relative_outputs
            ],
        }
        (review_dir / "boundary-review-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )
    return 0 if result["pass"] else 1


def _validate_protected_evidence(payload: object, evidence_root: Path) -> None:
    if not isinstance(payload, dict):
        return
    segments = payload.get("segments")
    if not isinstance(segments, list):
        return
    for segment in segments:
        if not isinstance(segment, dict) or segment.get("protected") is not True:
            continue
        raw_ref = segment.get("protected_evidence_ref")
        if not isinstance(raw_ref, str):
            raise ValueError("cut_boundary_protected_evidence_ref_invalid")
        ref = Path(raw_ref)
        if ref.is_absolute() or ".." in ref.parts:
            raise ValueError("cut_boundary_protected_evidence_ref_invalid")
        path = evidence_root / ref
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest()
            != segment.get("protected_evidence_sha256")
        ):
            raise ValueError("cut_boundary_protected_evidence_hash_mismatch")


if __name__ == "__main__":
    raise SystemExit(main())
