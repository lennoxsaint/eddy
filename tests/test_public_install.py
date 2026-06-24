import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_script_dry_run_lists_agent_skill_targets():
    env = {**os.environ, "EDDY_INSTALL_DRY_RUN": "1"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "install_agent_skill.py"), "--agent", "auto"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert str(ROOT) in proc.stdout
    assert ".codex/skills/eddy" in proc.stdout
    assert ".claude/skills/eddy" in proc.stdout
    assert ".agents/skills/eddy" in proc.stdout


def test_root_skill_exists_for_agent_install():
    skill = ROOT / "SKILL.md"
    text = skill.read_text()
    assert "name: eddy" in text
    assert "eddy run" in text


def test_install_script_provisions_studio_sound_by_default():
    script = ROOT / "scripts" / "install_agent_skill.py"
    text = script.read_text()
    assert "--skip-studio-sound" in text
    assert "studio-sound" in text
    assert "install_studio_sound=not args.skip_studio_sound" in text


def test_public_install_docs_use_github_source_not_occupied_pypi_name():
    docs = [
        ROOT / "README.md",
        ROOT / "docs" / "MCP.md",
        ROOT / "integrations" / "claude-code" / "README.md",
    ]
    for doc in docs:
        text = doc.read_text()
        assert "pipx install 'eddy[mcp]'" not in text
        assert "pip install 'eddy[mcp]'" not in text
        assert "git+https://github.com/lennoxsaint/eddy.git@v1.8.1" in text
