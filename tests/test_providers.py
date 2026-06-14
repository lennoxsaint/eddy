"""CLI provider behaviour: the Claude pairing-guard (exit 43) settle-retry."""

import subprocess
from types import SimpleNamespace

import pytest

from eddy.config import CliProviderConfig
from eddy.providers.base import ProviderError
from eddy.providers.cli_subprocess import CliProvider


def _proc(returncode, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _provider():
    return CliProvider(CliProviderConfig(binary="claude"), name="claude_cli")


def test_pairing_guard_settles_then_succeeds(monkeypatch):
    """Exit 43 is a one-time pairing correction: settle, retry, and succeed without
    consuming the normal retry budget."""
    monkeypatch.setattr("eddy.providers.cli_subprocess.shutil.which", lambda _b: "/usr/bin/claude")
    monkeypatch.setattr("eddy.providers.cli_subprocess.time.sleep", lambda _s: None)

    calls = []
    results = [
        _proc(43, stderr="Safety stop: corrected Claude Chrome pairing to MacBook-Pro-2 Chrome. Re-run the same command"),
        _proc(0, stdout="hello world"),
    ]

    def fake_run(*_a, **_k):
        calls.append(1)
        return results[len(calls) - 1]

    monkeypatch.setattr("eddy.providers.cli_subprocess.subprocess.run", fake_run)
    out = _provider().complete([{"role": "user", "content": "hi"}])
    assert out == "hello world"
    assert len(calls) == 2  # guard trip + successful retry


def test_settle_does_not_exhaust_real_retry_budget(monkeypatch):
    """A pairing trip followed by a genuine error still leaves the 2 real attempts intact."""
    monkeypatch.setattr("eddy.providers.cli_subprocess.shutil.which", lambda _b: "/usr/bin/claude")
    monkeypatch.setattr("eddy.providers.cli_subprocess.time.sleep", lambda _s: None)

    results = [
        _proc(43, stderr="corrected Claude Chrome pairing. Re-run the same command"),
        _proc(1, stderr="real failure"),
        _proc(1, stderr="real failure"),
    ]
    calls = []

    def fake_run(*_a, **_k):
        calls.append(1)
        return results[len(calls) - 1]

    monkeypatch.setattr("eddy.providers.cli_subprocess.subprocess.run", fake_run)
    with pytest.raises(ProviderError, match="real failure"):
        _provider().complete([{"role": "user", "content": "hi"}])
    # 1 guard trip (free) + 2 real attempts
    assert len(calls) == 3


def test_persistent_pairing_guard_eventually_fails(monkeypatch):
    """If the guard never settles, settle-retries are capped so we don't loop forever."""
    monkeypatch.setattr("eddy.providers.cli_subprocess.shutil.which", lambda _b: "/usr/bin/claude")
    monkeypatch.setattr("eddy.providers.cli_subprocess.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "eddy.providers.cli_subprocess.subprocess.run",
        lambda *_a, **_k: _proc(43, stderr="Re-run the same command"),
    )
    with pytest.raises(ProviderError, match="exited 43"):
        _provider().complete([{"role": "user", "content": "hi"}])
