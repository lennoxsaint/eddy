"""The tiny `eddy.log` diagnostic logger and the `ui.json_output` ledger helper.

Both exist to make best-effort failures debuggable without disturbing default behavior, so the
contract under test is precisely that: silent by default, opt-in on stderr, clean JSON on stdout.
"""

from __future__ import annotations

import json
import logging

import pytest

from eddy import log
from eddy.ui import console as ui


@pytest.fixture(autouse=True)
def _reset_logger():
    """The `eddy` logger is a process-global singleton; reset its config between tests."""
    yield
    eddy_logger = logging.getLogger("eddy")
    for handler in list(eddy_logger.handlers):
        eddy_logger.removeHandler(handler)
    log._configured = False


def _configure(monkeypatch, **env) -> logging.Logger:
    for key in ("EDDY_DEBUG", "EDDY_LOG"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    log._configured = False
    return log.logger()


def test_silent_by_default(monkeypatch):
    logger = _configure(monkeypatch)
    # NullHandler only, level above DEBUG → nothing surfaces.
    assert all(isinstance(h, logging.NullHandler) for h in logger.handlers)
    assert not logger.isEnabledFor(logging.DEBUG)


def test_eddy_debug_surfaces_on_stderr(monkeypatch, capsys):
    _configure(monkeypatch, EDDY_DEBUG="1")
    log.debug("probe failed: %s", "boom")
    captured = capsys.readouterr()
    assert captured.out == ""  # never stdout — keeps JSON ledgers parseable
    assert "probe failed: boom" in captured.err


def test_eddy_log_level_named(monkeypatch, capsys):
    logger = _configure(monkeypatch, EDDY_LOG="warning")
    assert logger.level == logging.WARNING
    log.debug("hidden below warning")
    assert "hidden" not in capsys.readouterr().err


def test_debug_never_raises(monkeypatch):
    _configure(monkeypatch)
    # A bad format string must not propagate — diagnostics can never break a run.
    log.debug("missing arg %s %s", "only-one")


def test_json_output_is_parseable_stdout(capsys):
    ui.json_output({"gate": "clean", "pass": True})
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"gate": "clean", "pass": True}
    assert captured.err == ""


def test_json_output_default_callable(capsys):
    from pathlib import Path

    ui.json_output({"path": Path("/tmp/x")}, default=str)
    assert json.loads(capsys.readouterr().out) == {"path": "/tmp/x"}
