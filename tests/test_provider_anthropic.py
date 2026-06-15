"""AnthropicProvider.complete behaviour with the SDK fully mocked.

The provider does `import anthropic`, constructs `anthropic.Anthropic(api_key=...)`, and calls
`client.messages.create(...)`. We monkeypatch `anthropic.Anthropic` with a fake client class and
feed canned `content` blocks (objects exposing `.type` and `.text`) so no network, no SDK auth, and
no real model are touched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from eddy.config import AnthropicConfig
from eddy.providers.base import ProviderError


def _block(text):
    return SimpleNamespace(type="text", text=text)


class _FakeMessages:
    def __init__(self, responses, calls):
        self._responses = list(responses)
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        item = self._responses[len(self._calls) - 1]
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(content=item)


class _FakeClientFactory:
    """Stands in for the `anthropic.Anthropic` class. Records the api_key it was constructed
    with and hands every instance the same scripted message responses + shared call log."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = []  # one dict of create() kwargs per attempt
        self.init_kwargs = []

    def __call__(self, **kwargs):
        self.init_kwargs.append(kwargs)
        return SimpleNamespace(messages=_FakeMessages(self._responses, self.calls))


def _install(monkeypatch, responses, *, with_key=True):
    """Patch anthropic.Anthropic and the env key. Returns the factory for assertions."""
    import anthropic

    factory = _FakeClientFactory(responses)
    monkeypatch.setattr(anthropic, "Anthropic", factory)
    if with_key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    from eddy.providers.anthropic_api import AnthropicProvider

    return AnthropicProvider(AnthropicConfig()), factory


def test_text_extraction_joins_only_text_blocks(monkeypatch):
    """Non-text blocks (e.g. tool_use) are dropped; the text blocks are concatenated in order."""
    content = [
        _block("Hello "),
        SimpleNamespace(type="tool_use", text="SHOULD_NOT_APPEAR"),
        _block("world"),
    ]
    provider, _ = _install(monkeypatch, [content])
    out = provider.complete([{"role": "user", "content": "hi"}])
    assert out == "Hello world"


def test_schema_path_returns_validated_dict(monkeypatch):
    """With a schema, JSON in a ```json fence is extracted and validated against the schema,
    returning the parsed dict (not the raw text)."""
    schema = {
        "type": "object",
        "required": ["score"],
        "properties": {"score": {"type": "number"}},
    }
    content = [_block('```json\n{"score": 9, "extra": "ok"}\n```')]
    provider, _ = _install(monkeypatch, [content])
    out = provider.complete([{"role": "user", "content": "judge it"}], schema=schema)
    assert out == {"score": 9, "extra": "ok"}


def test_schema_path_appends_json_instruction_to_last_message(monkeypatch):
    """Schema mode must rewrite ONLY the final message, appending the JSON-only instruction,
    and leave earlier messages untouched."""
    schema = {"type": "object", "required": ["k"], "properties": {"k": {"type": "string"}}}
    provider, factory = _install(monkeypatch, [[_block('{"k": "v"}')]])
    provider.complete(
        [
            {"role": "user", "content": "context msg"},
            {"role": "user", "content": "final ask"},
        ],
        schema=schema,
    )
    sent = factory.calls[0]["messages"]
    assert sent[0]["content"] == "context msg"  # earlier message untouched
    assert sent[1]["content"].startswith("final ask")
    assert "JSON object" in sent[1]["content"]


def test_invalid_schema_output_retries_then_raises_provider_error(monkeypatch):
    """Two structurally-wrong responses (missing the required key) exhaust both attempts and
    surface a ProviderError — and the provider really did call create() twice."""
    schema = {"type": "object", "required": ["score"], "properties": {"score": {"type": "number"}}}
    bad = [_block('{"not_score": 1}')]
    provider, factory = _install(monkeypatch, [bad, bad])
    with pytest.raises(ProviderError, match="anthropic failed after retry"):
        provider.complete([{"role": "user", "content": "x"}], schema=schema)
    assert len(factory.calls) == 2


def test_retry_recovers_on_second_attempt(monkeypatch):
    """A first attempt that raises is retried; a valid second attempt succeeds and is returned."""
    schema = {"type": "object", "required": ["score"], "properties": {"score": {"type": "number"}}}
    responses = [RuntimeError("transient 529 overloaded"), [_block('{"score": 7}')]]
    provider, factory = _install(monkeypatch, responses)
    out = provider.complete([{"role": "user", "content": "x"}], schema=schema)
    assert out == {"score": 7}
    assert len(factory.calls) == 2  # failed once, then succeeded


def test_configured_model_max_tokens_temperature_passed(monkeypatch):
    """Config defaults flow straight into create() when the call sites pass no overrides."""
    cfg = AnthropicConfig(model="claude-haiku-4-5-20251001", max_tokens=4096, temperature=0.3)
    import anthropic

    factory = _FakeClientFactory([[_block("ok")]])
    monkeypatch.setattr(anthropic, "Anthropic", factory)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    from eddy.providers.anthropic_api import AnthropicProvider

    AnthropicProvider(cfg).complete([{"role": "user", "content": "x"}])
    kw = factory.calls[0]
    assert kw["model"] == "claude-haiku-4-5-20251001"
    assert kw["max_tokens"] == 4096
    assert kw["temperature"] == 0.3


def test_explicit_overrides_beat_config_defaults(monkeypatch):
    """Per-call temperature/max_tokens override the configured defaults."""
    cfg = AnthropicConfig(max_tokens=4096, temperature=0.3)
    import anthropic

    factory = _FakeClientFactory([[_block("ok")]])
    monkeypatch.setattr(anthropic, "Anthropic", factory)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    from eddy.providers.anthropic_api import AnthropicProvider

    AnthropicProvider(cfg).complete(
        [{"role": "user", "content": "x"}], temperature=0.0, max_tokens=256
    )
    kw = factory.calls[0]
    assert kw["temperature"] == 0.0
    assert kw["max_tokens"] == 256


def test_api_key_from_env_passed_to_client(monkeypatch):
    """The api_key read from the configured env var is what gets handed to anthropic.Anthropic."""
    provider, factory = _install(monkeypatch, [[_block("ok")]])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-live-secret")
    provider.complete([{"role": "user", "content": "x"}])
    assert factory.init_kwargs[0]["api_key"] == "sk-live-secret"


def test_missing_api_key_raises_before_any_call(monkeypatch):
    """No key in either env var is a hard ProviderError, and the client is never constructed."""
    provider, factory = _install(monkeypatch, [[_block("ok")]], with_key=False)
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY not set"):
        provider.complete([{"role": "user", "content": "x"}])
    assert factory.init_kwargs == []
    assert factory.calls == []
