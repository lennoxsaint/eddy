"""recommend() recommendation matrix on synthetic detection dicts.

recommend(found) is a pure function over found = {hardware, ollama_models, credentials}.
These tests pin its priority ordering and message contents without touching detect()
(no subprocess / httpx / env reads).
"""

from eddy.doctor import LOCAL_TIER_MIN_RAM_GB, recommend

ALL_CREDS_FALSE = {
    "anthropic_api": False,
    "openai_api": False,
    "codex_cli": False,
    "claude_cli": False,
    "gemini_thumbnails": False,
}


def make_found(*, ram_gb=8, chip="Apple M2", models=None, **cred_overrides):
    creds = dict(ALL_CREDS_FALSE)
    creds.update(cred_overrides)
    return {
        "hardware": {"ram_gb": ram_gb, "chip": chip},
        "ollama_models": list(models or []),
        "credentials": creds,
    }


def test_local_model_with_enough_ram_picks_ollama():
    found = make_found(ram_gb=LOCAL_TIER_MIN_RAM_GB, chip="Apple M3 Max", models=["qwen2.5:32b"])
    provider, reason = recommend(found)
    assert provider == "ollama"
    # reason surfaces the actual hardware so the user sees why local was chosen
    assert "Apple M3 Max" in reason
    assert f"{LOCAL_TIER_MIN_RAM_GB}GB" in reason


def test_local_model_mid_ram_recommends_smaller_local_not_cloud():
    # v0.6 tiered: 16-32GB + a model recommends a SMALLER local model (free + private),
    # NOT a paid cloud provider (no hard 32GB cliff).
    found = make_found(ram_gb=16, models=["qwen2.5:7b"])
    provider, reason = recommend(found)
    assert provider == "ollama"
    assert "smaller local model" in reason
    assert "Install Ollama" not in reason  # it's the local tier, not the fallback


def test_local_model_very_low_ram_falls_through_to_fallback():
    # below the small floor (< 16GB), even with a model, fall through to the install/cloud guidance
    found = make_found(ram_gb=8, models=["qwen2.5:7b"])
    provider, reason = recommend(found)
    assert provider == "ollama"
    assert "Install Ollama" in reason
    assert "light for a strong local model" in reason  # guided note for the light machine


def test_enough_ram_but_no_models_falls_through_to_fallback():
    # 64GB RAM but zero local models: the local-tier branch requires BOTH.
    found = make_found(ram_gb=64, models=[])
    provider, reason = recommend(found)
    assert provider == "ollama"
    assert "Install Ollama" in reason


def test_codex_cli_chosen_when_no_local_setup():
    found = make_found(ram_gb=8, models=[], codex_cli=True)
    provider, reason = recommend(found)
    assert provider == "codex_cli"
    assert "codex CLI" in reason


def test_claude_cli_chosen_when_no_codex():
    found = make_found(ram_gb=8, models=[], claude_cli=True)
    provider, reason = recommend(found)
    assert provider == "claude_cli"
    assert "claude CLI" in reason


def test_codex_cli_outranks_claude_cli():
    # both CLIs present -> codex wins (checked first in the matrix)
    found = make_found(ram_gb=8, models=[], codex_cli=True, claude_cli=True)
    provider, _ = recommend(found)
    assert provider == "codex_cli"


def test_anthropic_key_chosen_over_openai():
    found = make_found(ram_gb=8, models=[], anthropic_api=True, openai_api=True)
    provider, reason = recommend(found)
    assert provider == "anthropic"
    assert "Anthropic API key" in reason


def test_openai_key_chosen_when_only_openai():
    found = make_found(ram_gb=8, models=[], openai_api=True)
    provider, reason = recommend(found)
    assert provider == "openai"
    assert "OpenAI API key" in reason


def test_cli_outranks_api_keys():
    # codex CLI present alongside both API keys -> CLI subscription path preferred
    found = make_found(
        ram_gb=8, models=[], codex_cli=True, anthropic_api=True, openai_api=True
    )
    provider, _ = recommend(found)
    assert provider == "codex_cli"


def test_local_tier_outranks_everything_else():
    # strong local setup present alongside CLIs and API keys -> local still wins (free/unlimited)
    found = make_found(
        ram_gb=128,
        models=["qwen2.5:32b"],
        codex_cli=True,
        claude_cli=True,
        anthropic_api=True,
        openai_api=True,
    )
    provider, reason = recommend(found)
    assert provider == "ollama"
    assert "Install Ollama" not in reason  # the local-tier reason, not the fallback


def test_nothing_detected_returns_ollama_with_install_message():
    found = make_found(ram_gb=8, models=[])
    provider, reason = recommend(found)
    assert provider == "ollama"
    assert "Install Ollama" in reason
    # the fallback names every other escape hatch
    assert "ANTHROPIC_API_KEY" in reason
    assert "OPENAI_API_KEY" in reason


def test_gemini_thumbnails_credential_does_not_drive_recommendation():
    # gemini key is for thumbnails, not editorial brain: it must NOT pick a provider.
    found = make_found(ram_gb=8, models=[], gemini_thumbnails=True)
    provider, reason = recommend(found)
    assert provider == "ollama"
    assert "Install Ollama" in reason


def test_missing_ram_gb_key_treated_as_zero():
    # hardware dict without ram_gb (defensive default 0) -> never crosses the local floor
    found = {
        "hardware": {"chip": "unknown"},
        "ollama_models": ["qwen2.5:32b"],
        "credentials": dict(ALL_CREDS_FALSE),
    }
    provider, reason = recommend(found)
    assert provider == "ollama"
    assert "Install Ollama" in reason
