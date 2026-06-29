from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from eddy.one_sentence import prepare_edit
from eddy.routing import choose_route
from eddy.templates import select_template, template_registry


def _fake_manifest(run_dir: Path, source: Path) -> dict:
    manifest = {
        "slug": run_dir.name,
        "sources": {"camera": str(source)},
        "source_sha256": {"camera": "abc"},
        "config": {},
        "eddy_version": "test",
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def _fake_cfg() -> SimpleNamespace:
    return SimpleNamespace(
        loop=SimpleNamespace(max_run_cost_usd=0.0),
        shorts=SimpleNamespace(
            require_hook_playbook=False,
            hook_playbook_path="docs/references/short-form-hook-playbook.jsonl",
            hook_playbook_min_records=1000,
        )
    )


def test_template_registry_selects_dual_source_tutorial():
    sources = {"camera": Path("camera.mp4"), "screen": Path("screen.mp4")}
    template = select_template(sources)
    assert template.id == "talking_head_screen_tutorial"
    assert "shorts" in template.outputs
    assert "motion_collision" in template.qa_gates
    assert "talking_head_screen_tutorial" in template_registry()


def test_route_prefers_codex_cli_over_local_model():
    route = choose_route(
        {
            "hardware": {"ram_gb": 128},
            "ollama_models": ["qwen3:32b"],
            "credentials": {"codex_cli": True, "claude_cli": False, "openai_api": False, "anthropic_api": False},
        }
    )
    assert route.can_execute is True
    assert route.tier == "api_agent_brain"
    assert route.provider == "codex_cli"


def test_route_blocks_with_exact_reason_when_no_brain():
    route = choose_route(
        {
            "hardware": {"ram_gb": 8},
            "ollama_models": [],
            "credentials": {"codex_cli": False, "claude_cli": False, "openai_api": False, "anthropic_api": False},
        }
    )
    assert route.can_execute is False
    assert route.blockers == ("no_editorial_brain_available",)


def test_prepare_edit_writes_support_bundle_for_exact_blocker(monkeypatch, tmp_path):
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"not real media but discovery is monkeypatched")
    run_dir = tmp_path / "runs" / "demo"
    manifest = _fake_manifest(run_dir, source)

    monkeypatch.setattr("eddy.one_sentence.load_config", lambda: _fake_cfg())
    monkeypatch.setattr("eddy.one_sentence.open_run", lambda *args, **kwargs: run_dir)
    monkeypatch.setattr("eddy.one_sentence.load_manifest", lambda rd: manifest)
    monkeypatch.setattr("eddy.one_sentence.discover_sources", lambda path: {"camera": source})
    monkeypatch.setattr("eddy.one_sentence.assert_sources_decodable", lambda sources: None)
    monkeypatch.setattr("eddy.one_sentence.verify_sources_unmutated", lambda m: None)
    monkeypatch.setattr("eddy.one_sentence._motion_cache_ready", lambda: True)
    monkeypatch.setattr("eddy.one_sentence.preflight", lambda: [{"check": "ffmpeg", "ok": True, "detail": "found"}])
    monkeypatch.setattr(
        "eddy.one_sentence.detect",
        lambda: {
            "hardware": {"ram_gb": 8},
            "ollama_models": [],
            "credentials": {"codex_cli": False, "claude_cli": False, "openai_api": False, "anthropic_api": False},
        },
    )
    monkeypatch.setattr(
        "eddy.one_sentence.edit_path_options",
        lambda *args, **kwargs: {
            "status": "blocked",
            "blockers": [
                {
                    "code": "no_edit_path_available",
                    "message": "No runnable editing path is available on this machine.",
                    "fix": "Use a host assistant or install a supported route.",
                }
            ],
            "selected_option_id": None,
            "fallback": {"order": []},
        },
    )

    result = prepare_edit(source, slug="demo", dry_run=True)
    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "no_edit_path_available"
    assert Path(result["support_bundle"]).exists()
    saved = json.loads((run_dir / "one-sentence-state.json").read_text())
    assert saved["support_bundle"] == result["support_bundle"]


def test_prepare_edit_ready_when_route_and_preflight_pass(monkeypatch, tmp_path):
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"not real media but discovery is monkeypatched")
    run_dir = tmp_path / "runs" / "demo"
    manifest = _fake_manifest(run_dir, source)

    monkeypatch.setattr("eddy.one_sentence.load_config", lambda: _fake_cfg())
    monkeypatch.setattr("eddy.one_sentence.open_run", lambda *args, **kwargs: run_dir)
    monkeypatch.setattr("eddy.one_sentence.load_manifest", lambda rd: manifest)
    monkeypatch.setattr("eddy.one_sentence.discover_sources", lambda path: {"camera": source})
    monkeypatch.setattr("eddy.one_sentence.assert_sources_decodable", lambda sources: None)
    monkeypatch.setattr("eddy.one_sentence.verify_sources_unmutated", lambda m: None)
    monkeypatch.setattr("eddy.one_sentence._motion_cache_ready", lambda: True)
    monkeypatch.setattr("eddy.one_sentence.preflight", lambda: [{"check": "ffmpeg", "ok": True, "detail": "found"}])
    monkeypatch.setattr(
        "eddy.one_sentence.detect",
        lambda: {
            "hardware": {"ram_gb": 8},
            "ollama_models": [],
            "credentials": {"codex_cli": True, "claude_cli": False, "openai_api": False, "anthropic_api": False},
        },
    )

    result = prepare_edit(source, slug="demo", dry_run=True)
    assert result["status"] == "ready"
    assert result["route"]["tier"] == "api_agent_brain"
    assert result["edit_options"]["recommended_option_id"] == "host_kernel"
    assert result["edit_options"]["requires_choice"] is False
    assert result["template"]["id"] == "single_camera_course"
    assert json.loads((run_dir / "one-sentence-state.json").read_text())["status"] == "ready"
