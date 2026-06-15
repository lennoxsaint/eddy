"""v0.6: cross-platform hardware detection. Linux/Windows no longer report ram_gb=0 (which
mis-tiered them to cloud); an unmeasurable machine reports None (honest), not a false 0."""

import platform

from eddy.doctor import _detect_hardware, _linux_chip, _linux_ram_gb, recommend


def test_linux_ram_gb_parses_meminfo():
    assert _linux_ram_gb("MemTotal:       16384000 kB\nMemFree:  100 kB\n") == round(16384000 / 2**20)


def test_linux_ram_gb_missing_or_garbage_is_none():
    assert _linux_ram_gb("MemFree: 100 kB") is None
    assert _linux_ram_gb("MemTotal: notanumber kB") is None


def test_linux_chip_parses_model_name():
    assert _linux_chip("processor : 0\nmodel name\t: AMD Ryzen 9 5900X\n") == "AMD Ryzen 9 5900X"


def test_linux_chip_unknown_when_absent():
    assert _linux_chip("processor : 0\n") == "unknown"


def test_detect_hardware_measures_this_machine():
    hw = _detect_hardware()
    assert hw["platform"] == platform.system()
    assert isinstance(hw["ram_gb"], int) and hw["ram_gb"] > 0  # a real dev machine measures RAM


def test_recommend_does_not_claim_local_tier_on_unmeasured_ram():
    found = {
        "hardware": {"ram_gb": None, "chip": "x"},
        "ollama_models": ["qwen:q4"],
        "credentials": {"codex_cli": False, "claude_cli": False, "anthropic_api": False, "openai_api": False},
    }
    prov, reason = recommend(found)
    # falls through to the install/fallback message, not the "runs a local model well" tier
    assert "runs a local model well" not in reason
    assert "Install Ollama" in reason or prov in {"anthropic", "openai", "codex_cli", "claude_cli"}
