"""Capability routing for Eddy's one-sentence editing flow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RoutePlan:
    tier: str
    provider: str
    can_execute: bool
    reason: str
    blockers: tuple[str, ...]
    fallback_order: tuple[str, ...]
    cloud_interface: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def choose_route(found: dict[str, Any], *, cloud_endpoint: str | None = None) -> RoutePlan:
    """Choose the safest honest execution route for the current machine."""

    hardware_raw = found.get("hardware")
    credentials_raw = found.get("credentials")
    hardware: dict[str, Any] = hardware_raw if isinstance(hardware_raw, dict) else found
    credentials: dict[str, Any] = credentials_raw if isinstance(credentials_raw, dict) else found
    ram_gb = int(hardware.get("ram_gb") or 0)
    local_ollama = bool(found.get("ollama") or found.get("ollama_models"))
    codex_cli = bool(credentials.get("codex_cli"))
    claude_cli = bool(credentials.get("claude_cli"))
    anthropic_key = bool(credentials.get("anthropic_api") or credentials.get("anthropic_key"))
    openai_key = bool(credentials.get("openai_api") or credentials.get("openai_key"))
    endpoint = cloud_endpoint

    fallback_order = (
        "api_agent_brain",
        "local_high_quality",
        "local_safe_slow",
        "eddy_cloud_interface",
        "exact_blocker",
    )

    if codex_cli or claude_cli or anthropic_key or openai_key:
        provider = (
            "codex_cli"
            if codex_cli
            else "claude_cli"
            if claude_cli
            else "anthropic_api"
            if anthropic_key
            else "openai_api"
        )
        return RoutePlan(
            tier="api_agent_brain",
            provider=provider,
            can_execute=True,
            reason=(
                "An agent/API brain is available for editorial judgment; raw media remains local "
                "and deterministic render gates still own pass/fail."
            ),
            blockers=(),
            fallback_order=fallback_order,
        )

    if local_ollama and ram_gb >= 32:
        return RoutePlan(
            tier="local_high_quality",
            provider="ollama",
            can_execute=True,
            reason="Local model runtime and enough memory are available for the strongest offline path.",
            blockers=(),
            fallback_order=fallback_order,
        )

    if local_ollama and ram_gb >= 16:
        return RoutePlan(
            tier="local_safe_slow",
            provider="ollama",
            can_execute=True,
            reason="Local model runtime is available, but Eddy should use the slower conservative profile.",
            blockers=(),
            fallback_order=fallback_order,
        )

    if endpoint:
        return RoutePlan(
            tier="eddy_cloud_interface",
            provider="eddy_cloud",
            can_execute=False,
            reason=(
                "A cloud endpoint was declared, but this open-source repo only exposes the interface. "
                "It will not start a paid or external job without an implemented runner and explicit approval."
            ),
            blockers=("eddy_cloud_runner_interface_only",),
            fallback_order=fallback_order,
            cloud_interface=endpoint,
        )

    return RoutePlan(
        tier="exact_blocker",
        provider="none",
        can_execute=False,
        reason="No Codex/Claude/API brain, local model runtime, or implemented cloud runner was found.",
        blockers=("no_editorial_brain_available",),
        fallback_order=fallback_order,
    )
