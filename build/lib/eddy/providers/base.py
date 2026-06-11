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
                return json.loads(text[start : i + 1])
    raise ProviderError("unterminated JSON object in response")


def validate_against(schema: dict, data: dict) -> dict:
    """Minimal structural check: required top-level keys exist."""
    for key in schema.get("required", []):
        if key not in data:
            raise ProviderError(f"response missing required key {key!r}")
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
