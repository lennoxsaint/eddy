import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _slash(path: str) -> str:
    return path.replace("\\", "/")


def test_codex_installer_dry_run_installs_skill_python_and_mcp():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "install_codex.py"), "--dry-run", "--json", "--skip-studio-sound"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)

    assert payload["status"] == "preview"
    assert payload["python_install"] is True
    assert payload["studio_sound_install"] is False
    assert os.path.isabs(payload["python"])
    assert any(_slash(item["target"]).endswith("/.codex/skills/eddy") for item in payload["codex_skill"])

    commands = [" ".join(step["command"]) for step in payload["steps"] if step["type"] == "command"]
    assert any("pip install -e" in command and "[mcp]" in command for command in commands)
    assert any("mcp install --client codex --dry-run" in command for command in commands)

    wrapper = payload["mcp_wrapper"]
    assert _slash(wrapper["path"]).endswith("/.eddy/bin/eddy-mcp")
    assert "-m eddy.mcp_server.server" in wrapper["content_preview"]

    mcp = payload["codex_mcp"]
    assert _slash(mcp["path"]).endswith("/.codex/config.toml")
    assert _slash(mcp["command"]).endswith("/.eddy/bin/eddy-mcp")
    assert "[mcp_servers.eddy]" in mcp["content_preview"]
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" not in json.dumps(mcp)


def test_codex_installer_can_preview_without_python_install():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "install_codex.py"), "--dry-run", "--json", "--skip-python-install"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["python_install"] is False
    assert _slash(payload["codex_mcp"]["command"]).endswith("/.eddy/bin/eddy-mcp")
    assert not [step for step in payload["steps"] if "pip" in " ".join(step.get("command", []))]


def test_codex_install_docs_are_plugin_first_with_skill_mcp_fallback():
    docs = (ROOT / "docs" / "CODEX_INSTALL.md").read_text()
    assert "@plugin-creator install [lennoxsaint/eddy](https://github.com/lennoxsaint/eddy)" in docs
    assert "plugins/eddy" in docs
    assert "latest stable tag" in docs
    assert "python3 scripts/install_codex.py" in docs
    assert "skill plus MCP fallback" in docs
