#!/usr/bin/env python3
"""Create or preview a Codex marketplace entry for the Eddy plugin."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/lennoxsaint/eddy.git"
PLUGIN_PATH = "./plugins/eddy"


def parse_version(tag: str) -> tuple[int, int, int] | None:
    if tag.startswith("v"):
        tag = tag[1:]
    parts = tag.split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except ValueError:
        return None


def current_version_tag() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return f"v{data['project']['version']}"


def remote_latest_tag(repo_url: str) -> str | None:
    proc = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", repo_url, "refs/tags/v*"],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if proc.returncode != 0:
        return None
    tags: list[tuple[tuple[int, int, int], str]] = []
    for line in proc.stdout.splitlines():
        tag = line.split()[-1].removeprefix("refs/tags/") if line.split() else ""
        parsed = parse_version(tag)
        if parsed is not None:
            tags.append((parsed, tag))
    return sorted(tags)[-1][1] if tags else None


def select_ref(repo_url: str, explicit_ref: str | None) -> tuple[str, str]:
    if explicit_ref:
        return explicit_ref, "explicit"
    current = current_version_tag()
    remote = remote_latest_tag(repo_url)
    if remote is None:
        return current, "current_version_pending_or_offline"
    current_parsed = parse_version(current)
    remote_parsed = parse_version(remote)
    if current_parsed and remote_parsed and current_parsed > remote_parsed:
        return current, "current_version_pending_tag"
    return remote, "latest_remote_stable_tag"


def marketplace_entry(ref: str, repo_url: str) -> dict:
    return {
        "name": "eddy",
        "source": {
            "source": "git-subdir",
            "url": repo_url,
            "path": PLUGIN_PATH,
            "ref": ref,
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": "Creativity",
    }


def merge_marketplace(path: Path, entry: dict) -> dict:
    if path.exists():
        payload = json.loads(path.read_text())
    else:
        payload = {
            "name": "lennoxsaint-plugins",
            "interface": {"displayName": "Lennox Saint Plugins"},
            "plugins": [],
        }
    plugins = [plugin for plugin in payload.get("plugins", []) if plugin.get("name") != "eddy"]
    plugins.append(entry)
    payload["plugins"] = plugins
    payload.setdefault("interface", {}).setdefault("displayName", "Lennox Saint Plugins")
    payload.setdefault("name", "lennoxsaint-plugins")
    return payload


def deeplink(plugin: str, marketplace_path: Path, *, share: bool = False) -> str:
    mode = "&mode=share" if share else ""
    return f"codex://plugins/{quote(plugin)}?marketplacePath={quote(str(marketplace_path))}{mode}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing marketplace.json.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--repo-url", default=REPO_URL)
    parser.add_argument("--ref", default=None, help="Stable tag to pin, for example v1.10.1.")
    parser.add_argument(
        "--marketplace-path",
        default=str(Path.home() / ".agents" / "plugins" / "marketplace.json"),
        help="Marketplace JSON path to create/update.",
    )
    args = parser.parse_args(argv)

    ref, ref_source = select_ref(args.repo_url, args.ref)
    marketplace_path = Path(args.marketplace_path).expanduser().resolve()
    entry = marketplace_entry(ref, args.repo_url)
    merged = merge_marketplace(marketplace_path, entry)
    if not args.dry_run:
        marketplace_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = marketplace_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, indent=2) + "\n")
        tmp.replace(marketplace_path)

    payload = {
        "status": "preview" if args.dry_run else "updated",
        "dry_run": args.dry_run,
        "marketplace_path": str(marketplace_path),
        "ref": ref,
        "ref_source": ref_source,
        "entry": entry,
        "marketplace": merged,
        "view_deeplink": deeplink("eddy", marketplace_path),
        "share_deeplink": deeplink("eddy", marketplace_path, share=True),
        "next_prompt": "@plugin-creator install [lennoxsaint/eddy](https://github.com/lennoxsaint/eddy)",
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Eddy Codex plugin marketplace {payload['status']}: {marketplace_path}")
        print(f"Ref: {ref} ({ref_source})")
        print(payload["view_deeplink"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
