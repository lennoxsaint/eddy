import ast
import os
import re
import subprocess
import sys
import tomllib
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
    payload = ast.literal_eval(proc.stdout)
    assert Path(payload["repo"]) == ROOT
    targets = [Path(item).as_posix() for item in payload["targets"]]
    assert any(target.endswith("/.codex/skills/eddy") for target in targets)
    assert any(target.endswith("/.claude/skills/eddy") for target in targets)
    assert any(target.endswith("/.agents/skills/eddy") for target in targets)


def test_root_skill_exists_for_agent_install():
    skill = ROOT / "SKILL.md"
    text = skill.read_text()
    assert "name: eddy" in text
    assert "eddy edit" in text
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
        assert re.search(r"git\+https://github\.com/lennoxsaint/eddy\.git@(main|v\d+\.\d+\.\d+)", text)


def test_public_source_install_pins_match_project_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    expected_tag = f"v{version}"
    docs = [
        ROOT / "README.md",
        ROOT / "docs" / "MCP.md",
        ROOT / "docs" / "RELEASE.md",
        ROOT / "integrations" / "claude-code" / "README.md",
    ]

    for doc in docs:
        text = doc.read_text()
        pins = re.findall(r"git\+https://github\.com/lennoxsaint/eddy\.git@(v\d+\.\d+\.\d+)", text)
        assert pins, f"{doc.relative_to(ROOT)} should include a tagged GitHub source install"
        assert all(pin == expected_tag for pin in pins), (
            f"{doc.relative_to(ROOT)} should pin public source installs to {expected_tag}; found {pins}"
        )
