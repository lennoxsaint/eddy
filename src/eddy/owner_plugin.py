"""Owner-channel and ChatGPT app-server proof for Eddy's personal plugin."""

from __future__ import annotations

import hashlib
import json
import select
import subprocess
import time
from pathlib import Path
from typing import Any


PLUGIN_VERSION = "3.0.0"


def owner_plugin_status(canonical_root: Path) -> dict[str, Any]:
    marketplace = Path.home() / ".agents" / "plugins" / "marketplace.json"
    owner_source = Path.home() / "plugins" / "eddy"
    canonical_plugin = canonical_root / "plugins" / "eddy"
    cache = Path.home() / ".codex" / "plugins" / "cache" / "personal" / "eddy" / PLUGIN_VERSION
    entry: dict[str, Any] | None = None
    if marketplace.exists():
        try:
            payload = json.loads(marketplace.read_text())
            entry = next(
                (row for row in payload.get("plugins", []) if row.get("name") == "eddy"),
                None,
            )
        except (json.JSONDecodeError, OSError):
            entry = None
    expected_source = {"source": "local", "path": "./plugins/eddy"}
    source_green = (
        owner_source.exists()
        and owner_source.is_symlink()
        and owner_source.resolve() == canonical_plugin.resolve()
    )
    marketplace_green = entry is not None and entry.get("source") == expected_source
    cache_green = cache.exists() and _tree_hashes(cache) == _tree_hashes(canonical_plugin)
    app_server = _app_server_probe(canonical_root)
    return {
        "version": PLUGIN_VERSION,
        "marketplace": str(marketplace),
        "marketplace_source": entry.get("source") if entry else None,
        "marketplace_ok": marketplace_green,
        "owner_source": str(owner_source),
        "owner_source_ok": source_green,
        "cache": str(cache),
        "cache_ok": cache_green,
        "app_server": app_server,
        "ok": marketplace_green and source_green and cache_green and bool(app_server.get("ok")),
    }


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _app_server_probe(canonical_root: Path) -> dict[str, Any]:
    binary = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if not binary.exists():
        return {"ok": False, "reason": "chatgpt_codex_binary_missing"}
    process = subprocess.Popen(
        [str(binary), "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdin is not None and process.stdout is not None
    requests = (
        {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "eddy-sync-doctor", "version": PLUGIN_VERSION},
                "capabilities": {"experimentalApi": True},
            },
        },
        {"method": "initialized"},
        {"id": 2, "method": "plugin/list", "params": {}},
        {
            "id": 3,
            "method": "plugin/read",
            "params": {
                "pluginName": "eddy",
                "marketplacePath": str(Path.home() / ".agents" / "plugins" / "marketplace.json"),
            },
        },
        {
            "id": 4,
            "method": "skills/list",
            "params": {"cwds": [str(canonical_root)], "forceReload": True},
        },
    )
    try:
        for request in requests:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
        responses: dict[int, dict[str, Any]] = {}
        deadline = time.time() + 20
        while time.time() < deadline and len(responses) < 4:
            ready, _, _ = select.select([process.stdout], [], [], 1)
            if not ready:
                continue
            line = process.stdout.readline()
            if not line:
                break
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(response.get("id"), int):
                responses[int(response["id"])] = response
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
    plugin = responses.get(3, {}).get("result", {}).get("plugin", {})
    summary = plugin.get("summary", {}) if isinstance(plugin, dict) else {}
    plugin_list = responses.get(2, {}).get("result", {}).get("marketplaces", [])
    listed = any(
        item.get("id") == "eddy@personal" and item.get("localVersion") == PLUGIN_VERSION
        for marketplace in plugin_list
        for item in marketplace.get("plugins", [])
        if isinstance(item, dict)
    )
    skill_rows = responses.get(4, {}).get("result", {}).get("data", [])
    skills = [
        skill
        for row in skill_rows
        for skill in row.get("skills", [])
        if isinstance(skill, dict) and skill.get("name") in {"eddy", "eddy:eddy"}
    ]
    skill_green = any(
        str(skill.get("path", "")).endswith("/eddy/3.0.0/skills/eddy/SKILL.md")
        and skill.get("enabled") is True
        for skill in skills
    )
    interface = summary.get("interface", {}) if isinstance(summary, dict) else {}
    read_green = (
        summary.get("id") == "eddy@personal"
        and summary.get("localVersion") == PLUGIN_VERSION
        and summary.get("installed") is True
        and summary.get("enabled") is True
        and interface.get("displayName") == "Eddy"
        and interface.get("brandColor") == "#F8BE34"
        and str(interface.get("composerIcon", "")).endswith("eddy-eagle-icon.png")
    )
    return {
        "ok": listed and read_green and skill_green,
        "plugin_list": listed,
        "plugin_read": read_green,
        "skills_list": skill_green,
        "local_version": summary.get("localVersion"),
        "display_name": interface.get("displayName"),
        "brand_color": interface.get("brandColor"),
        "composer_icon": interface.get("composerIcon"),
        "skill_paths": [skill.get("path") for skill in skills],
    }
