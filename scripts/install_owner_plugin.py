#!/usr/bin/env python3
"""Install Eddy's owner plugin from the canonical local V3 projection."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = Path.home() / ".agents" / "plugins" / "marketplace.json"
OWNER_SOURCE = Path.home() / "plugins" / "eddy"
OWNER_STATE = Path.home() / ".eddy" / "owner-channel.json"


def install(*, dry_run: bool) -> dict[str, object]:
    canonical_plugin = ROOT / "plugins" / "eddy"
    python = ROOT / ".venv" / "bin" / "python"
    if not canonical_plugin.exists() or not python.exists():
        raise RuntimeError("owner_plugin_canonical_runtime_missing")
    marketplace = json.loads(MARKETPLACE.read_text())
    eddy = next((row for row in marketplace.get("plugins", []) if row.get("name") == "eddy"), None)
    if eddy is None:
        raise RuntimeError("owner_plugin_marketplace_entry_missing")
    result: dict[str, object] = {
        "canonical_plugin": str(canonical_plugin),
        "marketplace": str(MARKETPLACE),
        "owner_source": str(OWNER_SOURCE),
        "dry_run": dry_run,
    }
    if dry_run:
        result["planned"] = [
            "backup personal marketplace",
            "link ~/plugins/eddy to canonical V3 plugin",
            "change Eddy marketplace source to local",
            "write owner-channel runtime receipt",
            "atomically reinstall eddy@personal",
        ]
        return result

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = MARKETPLACE.with_name(f"marketplace.backup-{stamp}.json")
    shutil.copy2(MARKETPLACE, backup)
    if OWNER_SOURCE.exists() or OWNER_SOURCE.is_symlink():
        if OWNER_SOURCE.is_symlink() and OWNER_SOURCE.resolve() == canonical_plugin.resolve():
            pass
        else:
            OWNER_SOURCE.rename(OWNER_SOURCE.with_name(f"eddy.backup-{stamp}"))
    if not OWNER_SOURCE.exists():
        OWNER_SOURCE.parent.mkdir(parents=True, exist_ok=True)
        OWNER_SOURCE.symlink_to(canonical_plugin, target_is_directory=True)
    eddy["source"] = {"source": "local", "path": "./plugins/eddy"}
    _atomic_json(MARKETPLACE, marketplace)

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    OWNER_STATE.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(
        OWNER_STATE,
        {
            "schema_version": "eddy-owner-channel-v1",
            "profile_id": "lennox-professional-youtube-v2",
            "canonical_root": str(ROOT),
            "canonical_commit": commit,
            "python": str(python),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
    binary = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    command = str(binary) if binary.exists() else "codex"
    subprocess.run([command, "plugin", "remove", "eddy@personal"], capture_output=True, text=True)
    added = subprocess.run(
        [command, "plugin", "add", "eddy@personal", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if added.returncode != 0:
        shutil.copy2(backup, MARKETPLACE)
        raise RuntimeError(f"owner_plugin_install_failed:{added.stderr[-800:]}")
    result.update(
        {
            "status": "installed",
            "marketplace_backup": str(backup),
            "install_result": json.loads(added.stdout),
            "owner_state": str(OWNER_STATE),
        }
    )
    return result


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(dry_run=args.dry_run), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
