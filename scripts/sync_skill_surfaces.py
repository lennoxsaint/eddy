#!/usr/bin/env python3
"""Generate or check Eddy's platform skill projections."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eddy.sync import CANONICAL_SURFACES, check_projection, write_projection  # noqa: E402

PROJECTIONS = (
    ROOT / "plugins" / "eddy" / "skills" / "eddy",
    ROOT / "integrations" / "claude-code" / "skills" / "eddy",
)


def commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    results = []
    for projection in PROJECTIONS:
        if args.check:
            result = check_projection(ROOT, projection, files=CANONICAL_SURFACES)
            results.append(
                {
                    "path": str(projection),
                    "ok": result.ok,
                    "missing": list(result.missing),
                    "changed": list(result.changed),
                }
            )
        else:
            manifest = write_projection(ROOT, projection, canonical_commit=commit())
            results.append({"path": str(projection), "ok": True, "manifest": str(manifest)})
    payload = {"status": "pass" if all(item["ok"] for item in results) else "failed", "results": results}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

