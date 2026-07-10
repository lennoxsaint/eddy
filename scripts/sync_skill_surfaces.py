#!/usr/bin/env python3
"""Generate or check Eddy's platform skill projections."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eddy.sync import (  # noqa: E402
    CANONICAL_SURFACES,
    canonical_surface_commit,
    check_projection,
    write_projection,
)

PROJECTIONS = (
    ROOT / "plugins" / "eddy" / "skills" / "eddy",
    ROOT / "integrations" / "claude-code" / "skills" / "eddy",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    results = []
    canonical_commit = canonical_surface_commit(ROOT)
    for projection in PROJECTIONS:
        if args.check:
            result = check_projection(
                ROOT,
                projection,
                files=CANONICAL_SURFACES,
                canonical_commit=canonical_commit,
            )
            results.append(
                {
                    "path": str(projection),
                    "ok": result.ok,
                    "missing": list(result.missing),
                    "changed": list(result.changed),
                    "extra": list(result.extra),
                    "manifest_commit_matches": result.manifest_commit_matches,
                }
            )
        else:
            manifest = write_projection(ROOT, projection, canonical_commit=canonical_commit)
            results.append({"path": str(projection), "ok": True, "manifest": str(manifest)})
    payload = {"status": "pass" if all(item["ok"] for item in results) else "failed", "results": results}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
