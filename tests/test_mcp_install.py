"""`eddy mcp install`: idempotent, backs up, merges only the eddy entry, never clobbers siblings."""

from __future__ import annotations

import json

import tomlkit

from eddy.mcp_server import install as inst


def test_render_json_merges_and_preserves_other_keys():
    existing = json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"})
    out = json.loads(inst.render_json(existing, "eddy-mcp"))
    assert out["mcpServers"]["eddy"] == {"command": "eddy-mcp", "args": []}
    assert out["mcpServers"]["other"] == {"command": "x"}  # sibling untouched
    assert out["theme"] == "dark"


def test_render_json_fresh():
    out = json.loads(inst.render_json(None, "eddy-mcp"))
    assert out["mcpServers"]["eddy"]["command"] == "eddy-mcp"


def test_render_toml_merges_and_preserves():
    existing = '[mcp_servers.other]\ncommand = "x"\n\n[settings]\nkey = 1\n'
    doc = tomlkit.parse(inst.render_toml(existing, "eddy-mcp"))
    assert doc["mcp_servers"]["eddy"]["command"] == "eddy-mcp"
    assert doc["mcp_servers"]["other"]["command"] == "x"
    assert doc["settings"]["key"] == 1


def test_install_creates_then_backs_up(tmp_path):
    target = tmp_path / "claude_desktop_config.json"
    first = inst.install("claude-desktop", path=target)
    assert first["action"] == "created" and target.exists()
    assert json.loads(target.read_text())["mcpServers"]["eddy"]["command"] == "eddy-mcp"

    # second install backs up the prior file and stays idempotent
    second = inst.install("claude-desktop", path=target, command="eddy-mcp")
    assert second["action"] == "updated"
    assert second["backup"] and (tmp_path / "claude_desktop_config.json.eddybak").exists()


def test_install_dry_run_writes_nothing(tmp_path):
    target = tmp_path / "config.toml"
    res = inst.install("codex", path=target, dry_run=True)
    assert res["action"] == "preview" and not target.exists()
    assert "eddy" in res["content"]


def test_install_codex_is_toml(tmp_path):
    target = tmp_path / "config.toml"
    inst.install("codex", path=target)
    doc = tomlkit.parse(target.read_text())
    assert doc["mcp_servers"]["eddy"]["command"] == "eddy-mcp"


def test_unknown_client_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown client"):
        inst.install("emacs", path=None)
