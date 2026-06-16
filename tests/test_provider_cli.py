"""v1.4: CliProvider (the codex/claude subscription-path adapter) — schema + text modes, path
redaction in errors, and the configured-transient-exit-code settle retry, which must NOT consume the
normal retry budget. subprocess.run is mocked so no real CLI runs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import eddy.providers.cli_subprocess as mod
from eddy.config import CliProviderConfig
from eddy.providers.base import ProviderError
from eddy.providers.cli_subprocess import CliProvider


def _fake_run(returncodes, stdout=""):
    """Return (calls, fn): fn yields the given exit codes in sequence; stdout may be str or per-call list."""
    calls = {"n": 0}

    def fn(argv, input=None, capture_output=None, text=None, timeout=None):
        i = calls["n"]
        calls["n"] += 1
        rc = returncodes[min(i, len(returncodes) - 1)]
        out = stdout if isinstance(stdout, str) else stdout[min(i, len(stdout) - 1)]
        return SimpleNamespace(returncode=rc, stdout=out, stderr="boom at /Users/x/secret/footage.mp4 failed")

    return calls, fn


def _provider(monkeypatch, fn, *, transient=None):
    monkeypatch.setattr(mod.shutil, "which", lambda b: "/usr/bin/" + b)
    monkeypatch.setattr(mod.subprocess, "run", fn)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    cfg = CliProviderConfig(binary="claude", transient_exit_codes=transient or [])
    return CliProvider(cfg, name="claude_cli")


def test_text_mode_returns_stripped_stdout(monkeypatch):
    _, fn = _fake_run([0], stdout="  hello world  ")
    p = _provider(monkeypatch, fn)
    assert p.complete([{"role": "user", "content": "hi"}]) == "hello world"


def test_schema_mode_validates_json(monkeypatch):
    _, fn = _fake_run([0], stdout='{"x": 1}')
    p = _provider(monkeypatch, fn)
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
    assert p.complete([{"role": "user", "content": "hi"}], schema=schema) == {"x": 1}


def test_not_installed_raises(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda b: None)
    p = CliProvider(CliProviderConfig(binary="claude"), name="claude_cli")
    with pytest.raises(ProviderError, match="not installed"):
        p.complete([{"role": "user", "content": "hi"}])


def test_nonzero_exit_redacts_paths_in_error(monkeypatch):
    _, fn = _fake_run([1], stdout="")
    p = _provider(monkeypatch, fn)
    with pytest.raises(ProviderError) as e:
        p.complete([{"role": "user", "content": "hi"}])
    msg = str(e.value)
    assert "[path]" in msg and "/Users/x/secret" not in msg  # PII path scrubbed before it reaches receipts


def test_transient_exit_code_settles_then_succeeds(monkeypatch):
    # a configured transient code retries WITHOUT consuming the retry budget, then succeeds
    calls, fn = _fake_run([42, 0], stdout=["", "ok text"])
    p = _provider(monkeypatch, fn, transient=[42])
    assert p.complete([{"role": "user", "content": "hi"}]) == "ok text"
    assert calls["n"] == 2


def test_retry_budget_exhausts_after_two_real_failures(monkeypatch):
    calls, fn = _fake_run([1, 1], stdout="")
    p = _provider(monkeypatch, fn)
    with pytest.raises(ProviderError, match="failed after retry"):
        p.complete([{"role": "user", "content": "hi"}])
    assert calls["n"] == 2
