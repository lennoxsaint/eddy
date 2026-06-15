"""Subscription-path adapters: shell out to the installed `codex` / `claude` CLIs
so a ChatGPT or Claude plan powers editing at no extra cost."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any

from eddy.config import CliProviderConfig
from eddy.providers.base import ProviderError, extract_json, validate_against

TIMEOUT_S = 1200

# Some local CLI wrappers exit with a "transient — re-run" code (e.g. a one-time auth/pairing
# settle) rather than a real failure. When a user configures such codes (provider.<cli>.
# transient_exit_codes), settle briefly and retry WITHOUT spending the normal retry budget, so a
# single transient blip never wastes the editorial call. Empty by default — no hardcoded behavior.
SETTLE_DELAY_S = 3.0
MAX_SETTLE_RETRIES = 2


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
        settle_used = 0
        attempts = 0
        while attempts < 2:
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
                    is_transient = proc.returncode in self.cfg.transient_exit_codes
                    if is_transient and settle_used < MAX_SETTLE_RETRIES:
                        # configured transient code: pause to settle, then retry without
                        # consuming the normal retry budget.
                        settle_used += 1
                        time.sleep(SETTLE_DELAY_S)
                        continue
                    raise ProviderError(f"{self.binary} exited {proc.returncode}: {detail}")
                text = proc.stdout.strip()
                if schema is None:
                    return text
                return validate_against(schema, extract_json(text))
            except (ProviderError, subprocess.TimeoutExpired, ValueError) as e:
                last_err = e
                attempts += 1
        raise ProviderError(f"{self.binary} failed after retry: {last_err}")
