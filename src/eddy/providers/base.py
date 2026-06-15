"""Provider protocol: one interface for all five brains.

complete(messages, schema=None) -> str when schema is None, else a dict validated
against `schema` (JSON Schema). Implementations must retry once on invalid JSON
before raising ProviderError.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from eddy.config import EddyConfig


class ProviderError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        messages: list[dict[str, str]],
        schema: dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any: ...


def _reject_nonfinite(token: str):
    # json.loads accepts bare NaN/Infinity/-Infinity by default; a NaN timestamp then
    # passes every numeric guard downstream and silently deletes content. Reject at the source.
    raise ProviderError(f"non-finite JSON constant {token!r} in model output")


def _loads_strict(text: str) -> dict:
    return json.loads(text, parse_constant=_reject_nonfinite)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of model text (handles ```json fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    if start < 0:
        raise ProviderError(f"no JSON object in response: {text[:200]!r}")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return _loads_strict(text[start : i + 1])
    raise ProviderError("unterminated JSON object in response")


def _is_numeric(v) -> bool:
    if isinstance(v, bool):
        return False  # a JSON true/false must not satisfy a number field
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):  # tolerate a stringified number; pydantic coerces it downstream
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _validate_node(schema: dict, data, path: str) -> None:
    t = schema.get("type")
    if t == "object":
        if not isinstance(data, dict):
            raise ProviderError(f"{path or 'response'}: expected object, got {type(data).__name__}")
        for key in schema.get("required", []):
            if key not in data:
                raise ProviderError(f"{path or 'response'}: missing required key {key!r}")
        for key, subschema in schema.get("properties", {}).items():
            if key in data:
                _validate_node(subschema, data[key], f"{path}.{key}" if path else key)
    elif t == "array":
        if not isinstance(data, list):
            raise ProviderError(f"{path or 'response'}: expected array, got {type(data).__name__}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(data):
                _validate_node(item_schema, item, f"{path}[{i}]")
    elif t in ("number", "integer"):
        if not _is_numeric(data):
            raise ProviderError(f"{path}: expected number, got {type(data).__name__}")
    elif t == "string":
        if not isinstance(data, str):
            raise ProviderError(f"{path}: expected string, got {type(data).__name__}")
    elif t == "boolean":
        if not isinstance(data, bool):
            raise ProviderError(f"{path}: expected boolean, got {type(data).__name__}")
    if "enum" in schema and data not in schema["enum"]:
        raise ProviderError(f"{path or 'response'}: {data!r} not in {schema['enum']}")


def validate_against(schema: dict, data: dict) -> dict:
    """Recursively validate model output against a JSON-Schema subset: NESTED required keys,
    container/scalar types, and enums (the old check was top-level keys only).

    This is the boundary that catches structurally-wrong model output — a judge missing a nested
    score dimension, a defect without a severity enum, a list where an object was required — and
    turns it into a ProviderError the provider retries on, instead of letting it crash or
    false-pass downstream. Numbers accept numeric strings; pydantic coerces them later.
    """
    _validate_node(schema, data, "")
    return data


def get_provider(cfg: EddyConfig, name: str | None = None) -> LLMProvider:
    active = name or cfg.provider.active
    if active == "ollama":
        from eddy.providers.ollama import OllamaProvider

        return OllamaProvider(cfg.provider.ollama)
    if active == "anthropic":
        from eddy.providers.anthropic_api import AnthropicProvider

        return AnthropicProvider(cfg.provider.anthropic)
    if active == "openai":
        from eddy.providers.openai_api import OpenAIProvider

        return OpenAIProvider(cfg.provider.openai)
    if active == "codex_cli":
        from eddy.providers.cli_subprocess import CliProvider

        return CliProvider(cfg.provider.codex_cli, name="codex_cli")
    if active == "claude_cli":
        from eddy.providers.cli_subprocess import CliProvider

        return CliProvider(cfg.provider.claude_cli, name="claude_cli")
    raise ProviderError(f"unknown provider {active!r}")


class FallbackProvider:
    """Editorial wrapper: try the upgraded brain; on ProviderError fall back to local so a
    run never hard-fails on a missing/unavailable subscription brain. Logs each fallback."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider, receipts=None):
        self.primary = primary
        self.fallback = fallback
        self.receipts = receipts
        self.name = f"{primary.name}->{fallback.name}"

    def complete(self, messages, schema=None, temperature=None, max_tokens=None):
        try:
            return self.primary.complete(messages, schema=schema, temperature=temperature, max_tokens=max_tokens)
        except ProviderError as e:
            if self.receipts is not None:
                self.receipts.log("editorial_fallback", primary=self.primary.name, fallback=self.fallback.name, error=str(e)[:200])
            return self.fallback.complete(messages, schema=schema, temperature=temperature, max_tokens=max_tokens)


def _editorial_available(cfg: EddyConfig) -> str | None:
    """First available stronger editorial brain: claude_cli (binary on PATH) > anthropic
    (API key present). None if no upgrade is available."""
    import os
    import shutil

    claude = cfg.provider.claude_cli
    if shutil.which(claude.binary or "claude"):
        return "claude_cli"
    if os.environ.get(cfg.provider.anthropic.api_key_env):
        return "anthropic"
    return None


_CLOUD_PROVIDERS = {"anthropic", "openai", "claude_cli", "codex_cli"}


def get_editorial_provider(cfg: EddyConfig, receipts=None) -> LLMProvider:
    """Resolve the brain for editorial-reasoning passes. Mechanical work (transcribe,
    render, QA) never calls this — it stays on the local default."""
    from eddy.privacy import is_offline

    setting = cfg.provider.editorial
    local = get_provider(cfg, cfg.provider.active)
    # --local-only / EDDY_OFFLINE: force the local brain so the transcript never leaves the
    # machine, regardless of editorial='auto' or a claude binary being on PATH.
    if is_offline():
        if receipts is not None:
            receipts.log("editorial_brain", chosen=cfg.provider.active, offline=True)
        return local
    if setting == "local":
        chosen = cfg.provider.active
    elif setting == "auto":
        chosen = _editorial_available(cfg) or cfg.provider.active
    else:
        chosen = setting
    if chosen == cfg.provider.active:
        if receipts is not None:
            receipts.log("editorial_brain", chosen=chosen, upgraded=False)
        return local
    primary = get_provider(cfg, chosen)
    if receipts is not None:
        # honest disclosure: a cloud brain means the transcript is sent off-device.
        receipts.log(
            "editorial_brain", chosen=chosen, upgraded=True, fallback=cfg.provider.active,
            egress=(chosen in _CLOUD_PROVIDERS),
        )
    return FallbackProvider(primary, local, receipts=receipts)
