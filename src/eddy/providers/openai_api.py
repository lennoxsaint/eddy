"""OpenAI API adapter."""

from __future__ import annotations

import os
from typing import Any

from eddy.config import OpenAIConfig
from eddy.providers.base import ProviderError, extract_json, validate_against


class OpenAIProvider:
    name = "openai"

    def __init__(self, cfg: OpenAIConfig, receipts=None):
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
            from openai import OpenAI
        except ImportError as e:
            raise ProviderError("pip install openai to use the OpenAI provider") from e

        key = os.environ.get(self.cfg.api_key_env)
        if not key:
            raise ProviderError(f"{self.cfg.api_key_env} not set")
        # actually pass the resolved key (+ base_url) so a CUSTOM api_key_env / Azure / proxy
        # endpoint works — the SDK's bare default only reads OPENAI_API_KEY.
        client_kwargs: dict = {"api_key": key}
        if self.cfg.base_url:
            client_kwargs["base_url"] = self.cfg.base_url
        client = OpenAI(**client_kwargs)

        kwargs: dict = {
            "model": self.cfg.model,
            "messages": messages,
            "max_completion_tokens": self.cfg.max_tokens if max_tokens is None else max_tokens,
        }
        # some reasoning models reject temperature; only send when explicitly configured
        temp = self.cfg.temperature if temperature is None else temperature
        if temp is not None:
            kwargs["temperature"] = temp
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
            kwargs["messages"] = messages[:-1] + [
                {
                    "role": messages[-1]["role"],
                    "content": messages[-1]["content"] + "\n\nRespond with ONLY a JSON object.",
                }
            ]

        last_err: Exception | None = None
        for _ in range(2):
            try:
                resp = client.chat.completions.create(**kwargs)
                text = resp.choices[0].message.content or ""
                u = getattr(resp, "usage", None)
                if u is not None:
                    from eddy.cost import log_cost

                    log_cost(self.receipts, "openai", self.cfg.model,
                             getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
                if schema is None:
                    return text
                return validate_against(schema, extract_json(text))
            except Exception as e:
                last_err = e
                if "temperature" in str(e) and "temperature" in kwargs:
                    kwargs.pop("temperature")
        raise ProviderError(f"openai failed after retry: {last_err}")
