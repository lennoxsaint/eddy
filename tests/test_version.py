"""v0.4: honest version. __version__ is git-tag-derived in a checkout (no longer the stale
hardcoded 0.1.0), and `eddy --version` reports it."""

import re

from typer.testing import CliRunner

import eddy
from eddy.cli import app

runner = CliRunner()


def test_version_is_nonempty_versionish_string():
    v = eddy.__version__
    assert isinstance(v, str) and v
    assert re.match(r"^\d", v)  # starts with a digit (a real version, not "unknown")


def test_version_reflects_git_tag_in_checkout():
    # this test runs from the git checkout, so the version should derive from `git describe`
    # off a real tag (v0.x...), not the old hardcoded "0.1.0".
    assert eddy.__version__ != "0.1.0"


def test_cli_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"eddy {eddy.__version__}"
