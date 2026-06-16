"""The wake command + mascot, end to end through the CLI. Bare `eddy` must wake the eagle; `--help`
and `--version` must still behave."""

from __future__ import annotations

from typer.testing import CliRunner

from eddy.cli import app

runner = CliRunner()


def test_bare_eddy_wakes_the_mascot():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "EDDY" in result.output
    assert "eddy run" in result.output  # next-step hints present


def test_version_still_works():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "eddy" in result.output.lower()


def test_help_still_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "mascot" in result.output and "run" in result.output


def test_mascot_state_renders():
    for state in ("idle", "thinking", "working", "success", "error"):
        result = runner.invoke(app, ["mascot", "--state", state, "--small"])
        assert result.exit_code == 0
        assert result.output.strip()


def test_mascot_default_shows_wake_screen():
    result = runner.invoke(app, ["mascot"])
    assert result.exit_code == 0
    assert "EDDY" in result.output
