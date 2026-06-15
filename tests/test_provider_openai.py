"""OpenAIProvider.complete: text/schema paths, retry->ProviderError, temperature-reject
recovery, and the v0.4 fix that the missing-key check honors the CONFIGURED api_key_env
(not a hardcoded OPENAI_API_KEY). All transport is mocked: no real client, no network.
"""

from types import SimpleNamespace

import openai
import pytest

from eddy.config import OpenAIConfig
from eddy.providers.base import ProviderError
from eddy.providers.openai_api import OpenAIProvider

MSGS = [{"role": "user", "content": "edit this"}]


def _resp(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class _FakeClient:
    """Records every chat.completions.create kwargs and replays scripted outcomes.

    Each entry in `outcomes` is either a content string (success) or an Exception
    (raised). The class attributes are reset per-provider via _install().
    """

    outcomes: list = []
    calls: list = []

    def __init__(self, *args, **kwargs):
        type(self).init_kwargs = kwargs

        class _Completions:
            def create(_self, **kw):
                type(self).calls.append(kw)
                out = type(self).outcomes[len(type(self).calls) - 1]
                if isinstance(out, Exception):
                    raise out
                return _resp(out)

        self.chat = SimpleNamespace(completions=_Completions())


def _install(monkeypatch, outcomes, env_key="OPENAI_API_KEY", env_value="sk-test"):
    _FakeClient.outcomes = outcomes
    _FakeClient.calls = []
    _FakeClient.init_kwargs = None
    monkeypatch.setattr(openai, "OpenAI", _FakeClient)
    if env_value is None:
        monkeypatch.delenv(env_key, raising=False)
    else:
        monkeypatch.setenv(env_key, env_value)
    return _FakeClient


def _provider(**overrides):
    return OpenAIProvider(OpenAIConfig(**overrides))


def test_text_path_returns_message_content(monkeypatch):
    """schema=None returns the raw assistant text from choices[0].message.content."""
    fake = _install(monkeypatch, ["here is your edit plan"])
    out = _provider().complete(MSGS)
    assert out == "here is your edit plan"
    assert len(fake.calls) == 1
    # max_tokens maps to max_completion_tokens (not the legacy max_tokens field)
    assert fake.calls[0]["max_completion_tokens"] == 4096
    assert "max_tokens" not in fake.calls[0]


def test_schema_path_validates_and_returns_dict(monkeypatch):
    """With a schema, the JSON in the response is extracted, validated, and returned;
    the request asks for json_object and appends the JSON-only instruction."""
    schema = {
        "type": "object",
        "required": ["score"],
        "properties": {"score": {"type": "number"}},
    }
    fake = _install(monkeypatch, ['```json\n{"score": 9}\n```'])
    out = _provider().complete(MSGS, schema=schema)
    assert out == {"score": 9}
    sent = fake.calls[0]
    assert sent["response_format"] == {"type": "json_object"}
    # the last user message is rewritten with the JSON-only directive
    assert sent["messages"][-1]["content"].endswith("Respond with ONLY a JSON object.")
    assert sent["messages"][-1]["content"].startswith("edit this")


def test_schema_validation_failure_retries_then_raises(monkeypatch):
    """Output missing a required key fails validation; provider retries once more, then
    raises ProviderError. Both attempts are real create() calls."""
    schema = {
        "type": "object",
        "required": ["score"],
        "properties": {"score": {"type": "number"}},
    }
    fake = _install(monkeypatch, ['{"wrong": 1}', '{"still": "wrong"}'])
    with pytest.raises(ProviderError, match="openai failed after retry"):
        _provider().complete(MSGS, schema=schema)
    assert len(fake.calls) == 2


def test_api_error_exhausts_retry_and_raises_with_cause(monkeypatch):
    """A transport-level exception on both attempts surfaces as ProviderError naming the
    last error, after exactly 2 attempts."""
    boom = RuntimeError("502 upstream blew up")
    fake = _install(monkeypatch, [boom, boom])
    with pytest.raises(ProviderError, match="502 upstream blew up"):
        _provider().complete(MSGS)
    assert len(fake.calls) == 2


def test_temperature_rejection_is_recovered(monkeypatch):
    """A reasoning model that rejects temperature: first call raises a temperature error,
    provider drops temperature and the retry succeeds. The 2nd request omits temperature."""
    err = RuntimeError("Unsupported value: 'temperature' is not supported")
    fake = _install(monkeypatch, [err, "recovered output"])
    out = _provider(temperature=0.7).complete(MSGS)
    assert out == "recovered output"
    assert len(fake.calls) == 2
    assert fake.calls[0].get("temperature") == 0.7
    assert "temperature" not in fake.calls[1]


def test_configured_temperature_is_sent(monkeypatch):
    """A configured temperature is forwarded on the first request (it is only dropped on a
    temperature-rejection retry, exercised separately)."""
    fake = _install(monkeypatch, ["ok"])
    out = _provider(temperature=0.42).complete(MSGS)
    assert out == "ok"
    assert fake.calls[0]["temperature"] == 0.42


def test_missing_key_uses_configured_env_var_not_hardcoded(monkeypatch):
    """v0.4 fix: the missing-key guard reads the CONFIGURED api_key_env. With a custom
    env var unset, the error names that var (not OPENAI_API_KEY) and no client is built."""
    fake = _install(monkeypatch, ["unused"], env_key="MY_OPENAI_KEY", env_value=None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="MY_OPENAI_KEY not set"):
        _provider(api_key_env="MY_OPENAI_KEY").complete(MSGS)
    # guard fires before the client is constructed / called
    assert fake.init_kwargs is None
    assert fake.calls == []


def test_custom_env_var_present_satisfies_guard(monkeypatch):
    """The flip side of the v0.4 fix: setting the CONFIGURED var (while OPENAI_API_KEY is
    absent) passes the guard. A hardcoded OPENAI_API_KEY check would wrongly fail here."""
    fake = _install(monkeypatch, ["done"], env_key="MY_OPENAI_KEY", env_value="sk-custom")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = _provider(api_key_env="MY_OPENAI_KEY").complete(MSGS)
    assert out == "done"
    assert len(fake.calls) == 1


def test_explicit_max_tokens_overrides_config(monkeypatch):
    """An explicit max_tokens arg overrides the config default and maps to
    max_completion_tokens."""
    fake = _install(monkeypatch, ["sized"])
    _provider(max_tokens=4096).complete(MSGS, max_tokens=128)
    assert fake.calls[0]["max_completion_tokens"] == 128


def test_resolved_key_is_passed_to_constructor(monkeypatch):
    """v0.5: the resolved key actually reaches OpenAI(api_key=...) instead of a bare OpenAI()."""
    fake = _install(monkeypatch, ["ok"], env_key="OPENAI_API_KEY", env_value="sk-xyz")
    _provider().complete(MSGS)
    assert fake.init_kwargs["api_key"] == "sk-xyz"
    assert "base_url" not in fake.init_kwargs  # none configured


def test_custom_env_var_key_reaches_constructor(monkeypatch):
    """A CUSTOM api_key_env value is read and passed — a bare OpenAI() would miss it."""
    fake = _install(monkeypatch, ["ok"], env_key="MY_OPENAI_KEY", env_value="sk-custom")
    _provider(api_key_env="MY_OPENAI_KEY").complete(MSGS)
    assert fake.init_kwargs["api_key"] == "sk-custom"


def test_base_url_passed_when_configured(monkeypatch):
    """A configured base_url (Azure / proxy / self-hosted) reaches the constructor."""
    fake = _install(monkeypatch, ["ok"], env_value="sk-test")
    _provider(base_url="https://proxy.example/v1").complete(MSGS)
    assert fake.init_kwargs["base_url"] == "https://proxy.example/v1"
