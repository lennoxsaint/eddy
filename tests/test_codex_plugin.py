import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_plugin_manifest_and_mcp_are_valid():
    plugin = json.loads((ROOT / "plugins" / "eddy" / ".codex-plugin" / "plugin.json").read_text())
    mcp = json.loads((ROOT / "plugins" / "eddy" / ".mcp.json").read_text())

    assert plugin["name"] == "eddy"
    assert plugin["version"] == "1.10.5"
    assert plugin["skills"] == "./skills/"
    assert plugin["mcpServers"] == "./.mcp.json"
    assert plugin["interface"]["displayName"] == "Eddy"
    assert len(plugin["interface"]["defaultPrompt"]) <= 3
    assert all(len(prompt) <= 128 for prompt in plugin["interface"]["defaultPrompt"])
    assert plugin["interface"]["brandColor"] == "#F8BE34"
    assert plugin["interface"]["composerIcon"] == "./assets/eddy-eagle-icon.png"
    assert plugin["interface"]["logo"] == "./assets/eddy-eagle-logo.png"

    for asset in ("eddy-eagle-icon.png", "eddy-eagle-logo.png"):
        asset_path = ROOT / "plugins" / "eddy" / "assets" / asset
        assert asset_path.exists()
        assert asset_path.stat().st_size > 0

    server = mcp["mcpServers"]["eddy"]
    assert server["cwd"] == "."
    assert server["command"] == "python3"
    assert server["args"] == ["./scripts/eddy_plugin_mcp.py"]


def test_repo_marketplace_uses_git_subdir_stable_tag():
    marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    [entry] = [plugin for plugin in marketplace["plugins"] if plugin["name"] == "eddy"]
    assert entry["source"] == {
        "source": "git-subdir",
        "url": "https://github.com/lennoxsaint/eddy.git",
        "path": "./plugins/eddy",
        "ref": "v1.10.5",
    }
    assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
    assert entry["category"] == "Creativity"


def test_install_codex_plugin_dry_run_preview(tmp_path):
    marketplace_path = tmp_path / "marketplace.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "install_codex_plugin.py"),
            "--dry-run",
            "--json",
            "--ref",
            "v1.10.5",
            "--marketplace-path",
            str(marketplace_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["status"] == "preview"
    assert payload["dry_run"] is True
    assert payload["ref"] == "v1.10.5"
    assert payload["entry"]["source"]["source"] == "git-subdir"
    assert payload["entry"]["source"]["path"] == "./plugins/eddy"
    assert payload["next_prompt"] == "@plugin-creator install [lennoxsaint/eddy](https://github.com/lennoxsaint/eddy)"
    assert not marketplace_path.exists()


def test_public_plugin_files_do_not_ship_local_paths():
    checked = [
        ROOT / "plugins" / "eddy" / ".codex-plugin" / "plugin.json",
        ROOT / "plugins" / "eddy" / ".mcp.json",
        ROOT / "plugins" / "eddy" / "skills" / "eddy" / "SKILL.md",
        ROOT / ".agents" / "plugins" / "marketplace.json",
    ]
    blob = "\n".join(path.read_text() for path in checked)
    assert "/Users/" + "lennoxsaint" not in blob
    assert "/Users/" + "yassybabes" not in blob
    assert "tf_mcp_" not in blob
