#!/usr/bin/env python3
"""Link owner agent skill folders to the canonical Eddy checkout with backups."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install(*, dry_run: bool) -> list[dict[str, str]]:
    targets = (
        Path.home() / ".claude" / "skills" / "eddy",
        Path.home() / ".codex" / "skills" / "eddy",
        Path.home() / ".agents" / "skills" / "eddy",
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results = []
    for target in targets:
        if target.exists() and target.resolve() == ROOT:
            action = "already_linked" if target.is_symlink() else "canonical_checkout"
            results.append({"target": str(target), "action": action})
            continue
        if dry_run:
            results.append({"target": str(target), "action": "would_backup_and_link"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            backup = target.with_name(f"eddy.backup-{stamp}")
            target.rename(backup)
        target.symlink_to(ROOT, target_is_directory=True)
        results.append({"target": str(target), "action": "linked"})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps({"canonical": str(ROOT), "results": install(dry_run=args.dry_run)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
