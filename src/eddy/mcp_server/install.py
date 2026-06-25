"""`eddy mcp install` — register the Eddy MCP server with Claude Desktop, Claude Code, or Codex.

Each writer is idempotent, backs the target file up before touching it, and merges only the ``eddy``
server entry so unrelated config is never clobbered. Writes are atomic (temp file + os.replace).
JSON for Claude Desktop / Claude Code (`.mcp.json`); TOML (via tomlkit, comment-preserving) for Codex.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_COMMAND = "eddy-mcp"
CLIENTS = ("claude-desktop", "claude-code", "codex")


def default_path(client: str) -> Path:
    """The conventional config path for a client (override with --path)."""
    home = Path.home()
    if client == "claude-desktop":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if client == "claude-code":
        return Path.cwd() / ".mcp.json"
    if client == "codex":
        return home / ".codex" / "config.toml"
    raise ValueError(f"unknown client {client!r}; choose one of {', '.join(CLIENTS)}")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _server_entry(command: str) -> dict:
    return {"command": command, "args": []}


def render_json(existing: str | None, command: str) -> str:
    """Merge the eddy server into an existing JSON config (or a fresh one), preserving other keys."""
    data = json.loads(existing) if existing and existing.strip() else {}
    data.setdefault("mcpServers", {})["eddy"] = _server_entry(command)
    return json.dumps(data, indent=2) + "\n"


def render_toml(existing: str | None, command: str) -> str:
    """Merge the eddy server into a Codex TOML config, preserving comments and other tables."""
    import tomlkit

    doc = tomlkit.parse(existing) if existing and existing.strip() else tomlkit.document()
    servers = doc.get("mcp_servers")
    if servers is None:
        servers = tomlkit.table()
        doc["mcp_servers"] = servers
    servers["eddy"] = {"command": command, "args": []}
    return tomlkit.dumps(doc)


def render_preview(client: str, command: str) -> str:
    """Return only the Eddy server stanza for safe dry-run output.

    The full merged config can contain unrelated user secrets in sibling MCP entries, so dry-run
    previews must never print the whole target file.
    """
    if client == "codex":
        return f"[mcp_servers.eddy]\ncommand = {json.dumps(command)}\nargs = []\n"
    return render_json(None, command)


def install(client: str, command: str = DEFAULT_COMMAND, path: Path | None = None, dry_run: bool = False) -> dict:
    """Write (or preview) the MCP registration for `client`. Returns a summary dict."""
    if client not in CLIENTS:
        raise ValueError(f"unknown client {client!r}; choose one of {', '.join(CLIENTS)}")
    target = Path(path) if path else default_path(client)
    existing = target.read_text() if target.exists() else None
    render = render_toml if client == "codex" else render_json
    content = render(existing, command)

    result = {
        "client": client,
        "path": str(target),
        "command": command,
        "dry_run": dry_run,
        "content_preview": render_preview(client, command),
        "existing_config_preserved": existing is not None,
    }
    if dry_run:
        result["action"] = "preview"
        return result

    backup = None
    if target.exists():
        backup = target.with_suffix(target.suffix + ".eddybak")
        backup.write_text(existing or "")
    _atomic_write(target, content)
    result["action"] = "updated" if existing is not None else "created"
    result["backup"] = str(backup) if backup else None
    return result
