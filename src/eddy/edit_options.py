"""Plain-English edit-path options for guided, proof-gated Eddy runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

FALLBACK_TRIGGERS = (
    "provider_timeout_or_stall",
    "provider_error",
    "repeated_non_green_gates_without_quality_gain",
    "repeated_same_qa_failure_signature",
)

_ALIASES = {
    "codex": "codex_cli",
    "codex-cli": "codex_cli",
    "claude": "claude_cli",
    "claude-code": "claude_cli",
    "claude-cli": "claude_cli",
    "local": "local_high_quality",
    "ollama": "local_high_quality",
    "openai": "openai_api",
    "anthropic": "anthropic_api",
    "host": "host_agent",
    "agent": "host_agent",
    "subscription": "host_agent",
}


@dataclass(frozen=True)
class EditPath:
    id: str
    label: str
    provider: str
    runnable: bool
    recommended: bool
    summary: str
    benefits: tuple[str, ...]
    drawbacks: tuple[str, ...]
    privacy: str
    cost: str
    unavailable_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_edit_path(edit_path: str | None, *, preferred_local: str = "local_high_quality") -> str | None:
    if not edit_path:
        return None
    key = edit_path.strip().lower().replace(" ", "_")
    normalized = _ALIASES.get(key, key)
    if normalized == "local_high_quality" and preferred_local == "local_safe_slow":
        return "local_safe_slow"
    return normalized


def provider_for_edit_path(edit_path: str | None) -> str | None:
    """Map an edit-path id to Eddy's provider setting, if it is a CLI/API/local provider."""

    if edit_path in {"codex_cli", "claude_cli"}:
        return edit_path
    if edit_path in {"local_high_quality", "local_safe_slow"}:
        return "ollama"
    if edit_path == "openai_api":
        return "openai"
    if edit_path == "anthropic_api":
        return "anthropic"
    return None


def _hardware(found: dict[str, Any]) -> dict[str, Any]:
    raw = found.get("hardware")
    return raw if isinstance(raw, dict) else found


def _credentials(found: dict[str, Any]) -> dict[str, Any]:
    raw = found.get("credentials")
    return raw if isinstance(raw, dict) else found


def _has_local(found: dict[str, Any]) -> bool:
    return bool(found.get("ollama") or found.get("ollama_models"))


def _metered_api_enabled(found: dict[str, Any], name: str) -> bool:
    credentials = _credentials(found)
    if name == "openai_api":
        return bool(credentials.get("openai_api") or credentials.get("openai_key"))
    if name == "anthropic_api":
        return bool(credentials.get("anthropic_api") or credentials.get("anthropic_key"))
    return False


def _option(
    option_id: str,
    label: str,
    provider: str,
    summary: str,
    benefits: tuple[str, ...],
    drawbacks: tuple[str, ...],
    privacy: str,
    cost: str,
    *,
    runnable: bool = True,
    recommended: bool = False,
    unavailable_reason: str = "",
) -> EditPath:
    return EditPath(
        id=option_id,
        label=label,
        provider=provider,
        runnable=runnable,
        recommended=recommended,
        summary=summary,
        benefits=benefits,
        drawbacks=drawbacks,
        privacy=privacy,
        cost=cost,
        unavailable_reason=unavailable_reason,
    )


def edit_path_options(
    found: dict[str, Any],
    *,
    source: Path | str | None = None,
    format: str = "youtube",
    focus: str | None = None,
    selected: str | None = None,
    auto_fallback: bool = True,
    fallback_policy: str = "agent_subscription",
    cost_cap_usd: float = 0.0,
    host_agent_available: bool = True,
) -> dict[str, Any]:
    """Return user-facing runnable edit paths plus setup suggestions.

    The output is intentionally plain JSON with nontechnical wording because MCP hosts display it
    directly before asking the user which way Eddy should edit.
    """

    hardware = _hardware(found)
    credentials = _credentials(found)
    ram_gb = int(hardware.get("ram_gb") or 0)
    local_id = "local_high_quality" if ram_gb >= 32 else "local_safe_slow"
    normalized_selected = normalize_edit_path(selected, preferred_local=local_id)

    options: list[EditPath] = []
    if host_agent_available:
        options.append(
            _option(
                "host_agent",
                "Use this assistant",
                "host_agent",
                "Eddy keeps the media local and asks the assistant you are already using to make the editing decisions.",
                (
                    "Best use of the subscription or agent session already in front of you.",
                    "Eddy still owns source hashing, rendering, QA, receipts, and blockers.",
                    "The cleanest fallback when a CLI model stalls.",
                ),
                (
                    "The transcript and QA packet are shown to the host assistant.",
                    "The assistant must submit structured decisions before Eddy can render.",
                ),
                "Raw media bytes stay local. Transcript and QA text go to the current assistant session.",
                "Usually included in the current assistant subscription; no metered API fallback is started.",
            )
        )

    if credentials.get("codex_cli"):
        options.append(
            _option(
                "codex_cli",
                "Use Codex CLI",
                "codex_cli",
                "Eddy asks your installed Codex command-line app for the editorial decisions.",
                (
                    "Good when Codex CLI is already signed in.",
                    "Runs without a separate OpenAI API bill.",
                    "Works headlessly inside Eddy's normal loop.",
                ),
                (
                    "Can stall on very long transcripts or local CLI auth issues.",
                    "Transcript text leaves the machine through the Codex CLI session.",
                ),
                "Raw media stays local; transcript text is sent through Codex CLI.",
                "Typically subscription-backed, not metered API usage.",
            )
        )

    if credentials.get("claude_cli"):
        options.append(
            _option(
                "claude_cli",
                "Use Claude CLI",
                "claude_cli",
                "Eddy asks your installed Claude command-line app for the editorial decisions.",
                (
                    "Good for long-form reasoning when Claude CLI is already signed in.",
                    "Runs without a separate Anthropic API bill.",
                    "Works headlessly inside Eddy's normal loop.",
                ),
                (
                    "Can be slower on repeated revision loops.",
                    "Transcript text leaves the machine through the Claude CLI session.",
                ),
                "Raw media stays local; transcript text is sent through Claude CLI.",
                "Typically subscription-backed, not metered API usage.",
            )
        )

    if _has_local(found):
        if ram_gb >= 32:
            options.append(
                _option(
                    "local_high_quality",
                    "Use local model",
                    "ollama",
                    "Eddy uses the best local model path it can find on this machine.",
                    (
                        "Most private option because the editorial brain stays on-device.",
                        "No per-run model API cost.",
                    ),
                    (
                        "Usually slower and less reliable on complex long edits than a strong host assistant.",
                        "May need more repair loops before gates pass.",
                    ),
                    "Raw media and transcript stay on this machine.",
                    "No API cost after local models are installed.",
                )
            )
        elif ram_gb >= 16:
            options.append(
                _option(
                    "local_safe_slow",
                    "Use local model, slower",
                    "ollama",
                    "Eddy uses the safer low-memory local path.",
                    (
                        "Private and free after local setup.",
                        "Can work when no subscription CLI is available.",
                    ),
                    (
                        "Slowest practical option.",
                        "More likely to need fallback for high-quality long edits.",
                    ),
                    "Raw media and transcript stay on this machine.",
                    "No API cost after local models are installed.",
                )
            )

    setup_suggestions: list[dict[str, str]] = []
    if not credentials.get("codex_cli"):
        setup_suggestions.append(
            {
                "id": "setup_codex_cli",
                "label": "Set up Codex CLI",
                "why": "Adds a subscription-backed headless route for Eddy's normal loop.",
                "drawback": "Requires installing/signing in to Codex CLI.",
            }
        )
    if not credentials.get("claude_cli"):
        setup_suggestions.append(
            {
                "id": "setup_claude_cli",
                "label": "Set up Claude CLI",
                "why": "Adds another subscription-backed fallback route.",
                "drawback": "Requires installing/signing in to Claude CLI.",
            }
        )
    if not _has_local(found):
        setup_suggestions.append(
            {
                "id": "setup_local_model",
                "label": "Set up local models",
                "why": "Adds the most private no-API-cost route.",
                "drawback": "Needs model downloads and enough memory; long edits can be slow.",
            }
        )

    for api_id, label in (("openai_api", "OpenAI API"), ("anthropic_api", "Anthropic API")):
        if _metered_api_enabled(found, api_id):
            if cost_cap_usd > 0:
                options.append(
                    _option(
                        api_id,
                        f"Use {label}",
                        "openai" if api_id == "openai_api" else "anthropic",
                        f"Eddy may use the metered {label} route within the configured run cap.",
                        ("Can be a strong fallback when subscription routes fail.",),
                        ("Metered spend is possible and must stay under the run-specific cap.",),
                        "Raw media stays local; transcript text is sent to the metered API.",
                        f"Allowed only up to this run's cap: ${cost_cap_usd:.2f}.",
                    )
                )
            else:
                setup_suggestions.append(
                    {
                        "id": f"{api_id}_needs_cost_cap",
                        "label": f"{label} key found, but not selectable",
                        "why": "Metered APIs are never automatic fallback without a run-specific cost cap.",
                        "drawback": "Set an explicit cap for this run if you want Eddy to use it.",
                    }
                )

    runnable = [option for option in options if option.runnable]
    recommended = "host_agent" if any(o.id == "host_agent" for o in runnable) else (runnable[0].id if runnable else None)
    if normalized_selected and not any(option.id == normalized_selected for option in runnable):
        setup_suggestions.insert(
            0,
            {
                "id": "selected_path_unavailable",
                "label": f"{selected} is not available",
                "why": "Eddy will use the recommended runnable path unless the user chooses another available path.",
                "drawback": "Unavailable paths are shown as setup suggestions, not choices.",
            },
        )
        normalized_selected = None

    selected_option = normalized_selected or recommended
    marked = [
        EditPath(
            **{
                **option.to_dict(),
                "recommended": option.id == recommended,
            }
        ).to_dict()
        for option in options
    ]

    order: list[str] = []
    for candidate in (
        selected_option,
        "host_agent" if fallback_policy == "agent_subscription" else None,
        "codex_cli",
        "claude_cli",
        local_id,
        "local_safe_slow" if local_id != "local_safe_slow" else None,
        "openai_api" if cost_cap_usd > 0 else None,
        "anthropic_api" if cost_cap_usd > 0 else None,
    ):
        if candidate and candidate not in order and any(o.id == candidate for o in runnable):
            order.append(candidate)

    blockers = []
    if not runnable:
        blockers.append(
            {
                "code": "no_edit_path_available",
                "message": "No runnable editing path is available on this machine.",
                "fix": "Use the current host assistant, sign in to Codex/Claude CLI, or install a supported local model.",
            }
        )

    return {
        "status": "ready" if runnable else "blocked",
        "source": str(Path(source).expanduser()) if source is not None else None,
        "format": format,
        "focus": focus or "",
        "question": "How do you want this edited?",
        "requires_choice": len(runnable) > 1 and normalized_selected is None,
        "recommended_option_id": recommended,
        "selected_option_id": selected_option,
        "options": marked,
        "setup_suggestions": setup_suggestions,
        "fallback": {
            "enabled": auto_fallback,
            "policy": fallback_policy,
            "order": order,
            "triggers": list(FALLBACK_TRIGGERS),
            "metered_api_requires_cost_cap": True,
        },
        "blockers": blockers,
    }
