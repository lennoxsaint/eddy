"""Ollama via its OpenAI-compatible endpoint. The default free-unlimited brain."""

from __future__ import annotations

from typing import Any

import httpx

from eddy.config import OllamaConfig
from eddy.providers.base import ProviderError, extract_json, validate_against


class OllamaProvider:
    name = "ollama"

    def __init__(self, cfg: OllamaConfig):
        self.cfg = cfg

    def complete(
        self,
        messages: list[dict[str, str]],
        schema: dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        body: dict = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "max_tokens": self.cfg.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if schema is not None:
            # Ollama supports structured outputs via `format` on the native API and
            # response_format on the OpenAI-compatible one; json_object is the widely
            # supported floor, schema enforcement is checked on our side.
            body["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        for _attempt in range(2):
            try:
                r = httpx.post(
                    f"{self.cfg.base_url}/chat/completions",
                    json=body,
                    timeout=httpx.Timeout(600, connect=10),
                )
                if r.status_code >= 400:
                    raise ProviderError(f"ollama {r.status_code}: {r.text[:500]}")
                text = r.json()["choices"][0]["message"]["content"]
                if schema is None:
                    return text
                return validate_against(schema, extract_json(text))
            except (ProviderError, httpx.HTTPError, KeyError, ValueError) as e:
                last_err = e
        raise ProviderError(f"ollama failed after retry: {last_err}")

    def models(self) -> list[str]:
        r = httpx.get(f"{self.cfg.base_url}/models", timeout=10)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]
