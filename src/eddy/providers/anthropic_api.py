"""Anthropic API adapter — cheapest capable Claude model by default."""

from __future__ import annotations

import os
from typing import Any

from eddy.config import AnthropicConfig
from eddy.providers.base import ProviderError, extract_json, validate_against


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, cfg: AnthropicConfig, receipts=None):
        self.cfg = cfg
        self.receipts = receipts

    def complete(
        self,
        messages: list[dict[str, str]],
        schema: dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError("pip install anthropic to use the Anthropic provider") from e

        api_key = os.environ.get(self.cfg.api_key_env) or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not api_key:
            raise ProviderError(f"{self.cfg.api_key_env} not set")
        client = anthropic.Anthropic(api_key=api_key)

        msgs = list(messages)
        if schema is not None:
            msgs = msgs[:-1] + [
                {
                    "role": msgs[-1]["role"],
                    "content": msgs[-1]["content"]
                    + "\n\nRespond with ONLY a JSON object matching the required schema. No prose.",
                }
            ]
        last_err: Exception | None = None
        for _ in range(2):
            try:
                resp = client.messages.create(
                    model=self.cfg.model,
                    max_tokens=self.cfg.max_tokens if max_tokens is None else max_tokens,
                    temperature=self.cfg.temperature if temperature is None else temperature,
                    messages=msgs,  # type: ignore[arg-type]  # plain dicts; SDK wants MessageParam
                )
                text = "".join(b.text for b in resp.content if b.type == "text")
                u = getattr(resp, "usage", None)
                if u is not None:
                    from eddy.cost import log_cost

                    log_cost(self.receipts, "anthropic", self.cfg.model,
                             getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0)
                if schema is None:
                    return text
                return validate_against(schema, extract_json(text))
            except Exception as e:  # SDK raises many types; retry once then surface
                last_err = e
        raise ProviderError(f"anthropic failed after retry: {last_err}")
