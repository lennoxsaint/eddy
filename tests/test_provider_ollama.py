"""OllamaProvider.complete() behaviour: schema-less text passthrough, schema validation,
retry-once semantics, NaN/Infinity rejection, and transport errors surfacing as ProviderError.

All HTTP is mocked at eddy.providers.ollama.httpx.post — no real Ollama server is contacted.
"""

from __future__ import annotations

import httpx
import pytest

from eddy.config import OllamaConfig
from eddy.providers.base import ProviderError
from eddy.providers.ollama import OllamaProvider


class _FakeResp:
    """Stand-in for httpx.Response carrying a chat-shaped payload."""

    def __init__(self, content: str = "", status_code: int = 200, text: str = ""):
        self._content = content
        self.status_code = status_code
        self.text = text or content

    def json(self):
        return {"message": {"content": self._content}}


def _provider() -> OllamaProvider:
    return OllamaProvider(OllamaConfig())


def _patch_post(monkeypatch, fn):
    """Route httpx.post used by the provider through `fn`; record every call's url+body."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, "json": kwargs.get("json")})
        return fn(len(calls) - 1, url, kwargs)

    monkeypatch.setattr("eddy.providers.ollama.httpx.post", fake_post)
    return calls


def test_plain_text_returned_when_schema_is_none(monkeypatch):
    """schema=None -> raw model text is returned verbatim, not parsed as JSON."""
    calls = _patch_post(
        monkeypatch, lambda i, url, kw: _FakeResp(content="just some prose, not json")
    )
    out = _provider().complete([{"role": "user", "content": "hi"}], schema=None)
    assert out == "just some prose, not json"
    assert len(calls) == 1  # one successful call, no retry
    assert calls[0]["url"].endswith("/api/chat")


def test_base_url_v1_suffix_stripped_in_request_url(monkeypatch):
    """The OpenAI '/v1' suffix is stripped so the native /api/chat endpoint is hit."""
    calls = _patch_post(monkeypatch, lambda i, url, kw: _FakeResp(content="ok"))
    OllamaProvider(OllamaConfig(base_url="http://host:11434/v1")).complete(
        [{"role": "user", "content": "hi"}]
    )
    assert calls[0]["url"] == "http://host:11434/api/chat"


def test_schema_request_includes_format_and_returns_validated_dict(monkeypatch):
    """A schema is sent as `format` and the parsed dict is run through validate_against."""
    schema = {
        "type": "object",
        "required": ["score"],
        "properties": {"score": {"type": "number"}},
    }
    calls = _patch_post(
        monkeypatch, lambda i, url, kw: _FakeResp(content='{"score": 7}')
    )
    out = _provider().complete([{"role": "user", "content": "x"}], schema=schema)
    assert out == {"score": 7}
    assert calls[0]["json"]["format"] == schema  # schema forwarded to Ollama


def test_schema_validation_failure_retries_once_then_raises(monkeypatch):
    """Model output missing a required key fails validation; provider retries exactly once
    (2 total attempts) then raises ProviderError."""
    schema = {
        "type": "object",
        "required": ["score"],
        "properties": {"score": {"type": "number"}},
    }
    # Both attempts return a dict that omits the required 'score' key.
    calls = _patch_post(
        monkeypatch, lambda i, url, kw: _FakeResp(content='{"verdict": "ok"}')
    )
    with pytest.raises(ProviderError, match="missing required key 'score'"):
        _provider().complete([{"role": "user", "content": "x"}], schema=schema)
    assert len(calls) == 2  # retry-once budget consumed


def test_non_json_then_valid_json_succeeds_on_second_attempt(monkeypatch):
    """First reply has no JSON object (raises in extract_json); the single retry recovers."""
    schema = {
        "type": "object",
        "required": ["ok"],
        "properties": {"ok": {"type": "boolean"}},
    }
    payloads = ["sorry, I cannot do that", '{"ok": true}']
    calls = _patch_post(
        monkeypatch, lambda i, url, kw: _FakeResp(content=payloads[i])
    )
    out = _provider().complete([{"role": "user", "content": "x"}], schema=schema)
    assert out == {"ok": True}
    assert len(calls) == 2  # first non-JSON failed, retry succeeded


def test_nan_in_model_output_is_rejected(monkeypatch):
    """A bare NaN constant must be rejected by extract_json's strict parse_constant; both
    attempts emit it, so the run ends in ProviderError, never a NaN-carrying dict."""
    schema = {
        "type": "object",
        "required": ["t"],
        "properties": {"t": {"type": "number"}},
    }
    calls = _patch_post(
        monkeypatch, lambda i, url, kw: _FakeResp(content='{"t": NaN}')
    )
    with pytest.raises(ProviderError, match="non-finite JSON constant"):
        _provider().complete([{"role": "user", "content": "x"}], schema=schema)
    assert len(calls) == 2


def test_infinity_in_model_output_is_rejected(monkeypatch):
    """Infinity is equally non-finite and must not survive parsing."""
    schema = {
        "type": "object",
        "required": ["t"],
        "properties": {"t": {"type": "number"}},
    }
    _patch_post(monkeypatch, lambda i, url, kw: _FakeResp(content='{"t": Infinity}'))
    with pytest.raises(ProviderError, match="non-finite JSON constant"):
        _provider().complete([{"role": "user", "content": "x"}], schema=schema)


def test_timeout_surfaces_as_provider_error(monkeypatch):
    """A read timeout (httpx.TimeoutException) is caught and re-raised as ProviderError
    after the retry budget; the original error is preserved in the message."""

    def boom(i, url, kw):
        raise httpx.ReadTimeout("read timed out")

    calls = _patch_post(monkeypatch, boom)
    with pytest.raises(ProviderError, match="ollama failed after retry"):
        _provider().complete([{"role": "user", "content": "x"}])
    assert len(calls) == 2


def test_connect_error_surfaces_as_provider_error(monkeypatch):
    """A transport/connection error (server down) becomes ProviderError, not a raw httpx error."""

    def boom(i, url, kw):
        raise httpx.ConnectError("connection refused")

    _patch_post(monkeypatch, boom)
    with pytest.raises(ProviderError, match="connection refused"):
        _provider().complete([{"role": "user", "content": "x"}])


def test_http_4xx_status_raises_provider_error_with_status(monkeypatch):
    """A >=400 status is turned into ProviderError carrying the status code, then retried once."""
    calls = _patch_post(
        monkeypatch,
        lambda i, url, kw: _FakeResp(status_code=500, text="internal boom"),
    )
    with pytest.raises(ProviderError, match="ollama failed after retry"):
        _provider().complete([{"role": "user", "content": "x"}])
    assert len(calls) == 2  # 500 raised, retried, raised again
