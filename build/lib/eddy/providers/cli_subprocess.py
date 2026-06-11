"""Subscription-path adapters: shell out to the installed `codex` / `claude` CLIs
so a ChatGPT or Claude plan powers editing at no extra cost."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from eddy.config import CliProviderConfig
from eddy.providers.base import ProviderError, extract_json, validate_against

TIMEOUT_S = 1200


class CliProvider:
    def __init__(self, cfg: CliProviderConfig, name: str):
        self.cfg = cfg
        self.name = name
        self.binary = cfg.binary or ("codex" if name == "codex_cli" else "claude")

    def _argv(self, prompt_via_stdin: bool) -> list[str]:
        if self.binary == "codex":
            argv = [self.binary, "exec", "--skip-git-repo-check"]
            if self.cfg.model:
                argv += ["-m", self.cfg.model]
            argv += ["-"]  # read prompt from stdin
            return argv
        # claude CLI
        argv = [self.binary, "-p", "--output-format", "text"]
        if self.cfg.model:
            argv += ["--model", self.cfg.model]
        return argv

    def complete(
        self,
        messages: list[dict[str, str]],
        schema: dict | None = None,
        temperature: float | None = None,  # CLIs do not expose temperature; accepted for protocol parity
        max_tokens: int | None = None,
    ) -> Any:
        if shutil.which(self.binary) is None:
            raise ProviderError(f"{self.binary} CLI not installed")

        prompt = "\n\n".join(m["content"] for m in messages)
        if schema is not None:
            prompt += (
                "\n\nRespond with ONLY a JSON object matching this JSON Schema (no prose, no fences):\n"
                + json.dumps(schema)
            )

        last_err: Exception | None = None
        for _ in range(2):
            try:
                proc = subprocess.run(
                    self._argv(prompt_via_stdin=True),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_S,
                )
                if proc.returncode != 0:
                    detail = (proc.stderr.strip() or proc.stdout.strip())[-500:]
                    raise ProviderError(f"{self.binary} exited {proc.returncode}: {detail}")
                text = proc.stdout.strip()
                if schema is None:
                    return text
                return validate_against(schema, extract_json(text))
            except (ProviderError, subprocess.TimeoutExpired, ValueError) as e:
                last_err = e
        raise ProviderError(f"{self.binary} failed after retry: {last_err}")
