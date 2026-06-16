"""Guard the Claude Code plugin bundle: valid JSON, the eddy-mcp registration, and the commands +
skill it ships. Cheap structural checks so a typo can't silently ship a broken plugin."""

from __future__ import annotations

import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "integrations" / "claude-code"


def test_manifest_valid():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "eddy"
    assert manifest["version"] and isinstance(manifest["description"], str)


def test_mcp_json_registers_eddy_mcp():
    mcp = json.loads((PLUGIN / ".mcp.json").read_text())
    assert mcp["mcpServers"]["eddy"]["command"] == "eddy-mcp"


def test_commands_present_with_frontmatter():
    for name in ("eddy-run", "eddy-status", "eddy-shorts"):
        body = (PLUGIN / "commands" / f"{name}.md").read_text()
        assert body.startswith("---") and "description:" in body.split("---", 2)[1]


def test_skill_has_frontmatter():
    skill = (PLUGIN / "skills" / "eddy" / "SKILL.md").read_text()
    front = skill.split("---", 2)[1]
    assert "name: eddy" in front and "description:" in front


def test_hooks_json_valid():
    assert "hooks" in json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
