from __future__ import annotations

from eddy.loop.receipts import Receipts
from eddy.edit_options import edit_path_options, normalize_edit_path, provider_for_edit_path
from eddy.providers.base import FallbackProvider, ProviderError


def test_single_runnable_path_skips_choice():
    plan = edit_path_options(
        {
            "hardware": {"ram_gb": 64},
            "ollama_models": [],
            "credentials": {"codex_cli": False, "claude_cli": False, "openai_api": False, "anthropic_api": False},
        },
        host_agent_available=True,
    )
    assert plan["status"] == "ready"
    assert plan["requires_choice"] is False
    assert plan["selected_option_id"] == "host_kernel"


def test_host_kernel_default_skips_chooser_even_when_advanced_paths_exist():
    plan = edit_path_options(
        {
            "hardware": {"ram_gb": 64},
            "ollama_models": ["qwen"],
            "credentials": {"codex_cli": True, "claude_cli": True, "openai_api": False, "anthropic_api": False},
        },
        host_agent_available=True,
    )
    labels = {option["id"]: option["label"] for option in plan["options"]}
    assert plan["requires_choice"] is False
    assert plan["recommended_option_id"] == "host_kernel"
    assert labels["host_kernel"] == "Use this assistant"
    assert "codex_cli" not in labels
    assert all(option["benefits"] and option["drawbacks"] for option in plan["options"])


def test_explicit_advanced_path_is_selectable_without_becoming_default():
    plan = edit_path_options(
        {
            "hardware": {"ram_gb": 64},
            "ollama_models": ["qwen"],
            "credentials": {"codex_cli": True, "claude_cli": False, "openai_api": False, "anthropic_api": False},
        },
        selected="codex_cli",
        host_agent_available=True,
    )
    assert plan["requires_choice"] is False
    assert plan["recommended_option_id"] == "host_kernel"
    assert plan["selected_option_id"] == "codex_cli"
    assert "codex_cli" in {option["id"] for option in plan["options"]}


def test_host_unavailable_multiple_paths_still_requires_choice():
    plan = edit_path_options(
        {
            "hardware": {"ram_gb": 64},
            "ollama_models": ["qwen"],
            "credentials": {"codex_cli": True, "claude_cli": False, "openai_api": False, "anthropic_api": False},
        },
        host_agent_available=False,
    )
    assert plan["requires_choice"] is True
    assert {option["id"] for option in plan["options"]} >= {"codex_cli", "local_high_quality"}


def test_unavailable_better_routes_are_setup_suggestions_not_options():
    plan = edit_path_options(
        {
            "hardware": {"ram_gb": 8},
            "ollama_models": [],
            "credentials": {"codex_cli": False, "claude_cli": False, "openai_api": True, "anthropic_api": False},
        },
        host_agent_available=False,
        cost_cap_usd=0.0,
    )
    assert plan["status"] == "blocked"
    assert "openai_api" not in {option["id"] for option in plan["options"]}
    assert "openai_api_needs_cost_cap" in {item["id"] for item in plan["setup_suggestions"]}


def test_metered_api_allowed_only_with_cost_cap():
    plan = edit_path_options(
        {
            "hardware": {"ram_gb": 8},
            "ollama_models": [],
            "credentials": {"codex_cli": False, "claude_cli": False, "openai_api": True, "anthropic_api": False},
        },
        host_agent_available=False,
        cost_cap_usd=3.0,
    )
    assert plan["status"] == "ready"
    assert "openai_api" in {option["id"] for option in plan["options"]}


def test_provider_mapping_for_cli_flags():
    assert normalize_edit_path("host_agent") == "host_kernel"
    assert normalize_edit_path("legacy-autonomous") == "legacy_autonomous"
    assert provider_for_edit_path("codex_cli") == "codex_cli"
    assert provider_for_edit_path("claude_cli") == "claude_cli"
    assert provider_for_edit_path("local_safe_slow") == "ollama"
    assert provider_for_edit_path("host_kernel") is None
    assert provider_for_edit_path("legacy_autonomous") is None


def test_provider_failure_writes_route_fallback_receipt(tmp_path):
    class Primary:
        name = "codex_cli"

        def complete(self, *args, **kwargs):
            raise ProviderError("stalled")

    class Local:
        name = "ollama"

        def complete(self, *args, **kwargs):
            return {"ok": True}

    receipts = Receipts(tmp_path)
    provider = FallbackProvider(Primary(), Local(), receipts=receipts)
    assert provider.complete([]) == {"ok": True}
    events = receipts.read()
    assert any(event["event"] == "route_fallback" and event["reason"] == "provider_error" for event in events)
