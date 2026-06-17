"""Ollama provider — the default free-unlimited brain.

Uses Ollama's NATIVE /api/chat (not the OpenAI-compatible shim) for two reasons:
- `options.num_ctx` must be explicit or long transcripts get silently truncated
  at the model's default context;
- `format` accepts a full JSON Schema (real structured outputs).
"""

from __future__ import annotations

from typing import Any

import httpx

from eddy.config import OllamaConfig
from eddy.providers.base import ProviderError, extract_json, validate_against


class OllamaProvider:
    name = "ollama"

    def __init__(self, cfg: OllamaConfig):
        self.cfg = cfg
        self.root = cfg.base_url.removesuffix("/v1").rstrip("/")

    def _adaptive_num_ctx(self, messages: list[dict[str, str]], num_predict: int) -> int:
        """Grow num_ctx for a long prompt so input + requested output both fit, capped at num_ctx_max.
        A 60-min+ transcript otherwise overruns the 32768 default and the model truncates its JSON
        mid-object. Short prompts return the configured default unchanged. ~4 chars/token estimate
        with headroom, rounded up to a 4096 boundary."""
        if not self.cfg.num_ctx_max or self.cfg.num_ctx_max <= self.cfg.num_ctx:
            return self.cfg.num_ctx
        est_input = sum(len(m.get("content", "")) for m in messages) // 4
        needed = est_input + num_predict + 2048  # headroom for the chat template + safety
        if needed <= self.cfg.num_ctx:
            return self.cfg.num_ctx
        rounded = ((needed + 4095) // 4096) * 4096
        return max(self.cfg.num_ctx, min(self.cfg.num_ctx_max, rounded))

    def complete(
        self,
        messages: list[dict[str, str]],
        schema: dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        num_predict = self.cfg.max_tokens if max_tokens is None else max_tokens
        body: dict = {
            "model": self.cfg.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.cfg.temperature if temperature is None else temperature,
                "num_predict": num_predict,
                "num_ctx": self._adaptive_num_ctx(messages, num_predict),
            },
        }
        if self.cfg.seed is not None:  # exact reproducibility: pin the sampler seed (use with temperature=0)
            body["options"]["seed"] = self.cfg.seed
        if schema is not None:
            body["format"] = schema

        last_err: Exception | None = None
        for _attempt in range(2):
            try:
                r = httpx.post(
                    f"{self.root}/api/chat",
                    json=body,
                    timeout=httpx.Timeout(1200, connect=10),
                )
                if r.status_code >= 400:
                    raise ProviderError(f"ollama {r.status_code}: {r.text[:500]}")
                text = r.json()["message"]["content"]
                if schema is None:
                    return text
                return validate_against(schema, extract_json(text))
            except (ProviderError, httpx.HTTPError, KeyError, ValueError) as e:
                last_err = e
        raise ProviderError(f"ollama failed after retry: {last_err}")

    def models(self) -> list[str]:
        r = httpx.get(f"{self.root}/api/tags", timeout=10)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
