import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "plugins" / "eddy" / "scripts" / "eddy_plugin_bootstrap.py"


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("eddy_plugin_bootstrap_test", BOOTSTRAP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_plugin_is_named_eddy_and_launches_managed_wrapper() -> None:
    manifest = json.loads((ROOT / "plugins" / "eddy" / ".codex-plugin" / "plugin.json").read_text())
    mcp = json.loads((ROOT / "plugins" / "eddy" / ".mcp.json").read_text())

    assert manifest["name"] == "eddy"
    assert manifest["interface"]["displayName"] == "Eddy"
    assert manifest["version"] == "3.0.0"
    assert manifest["repository"] == "https://github.com/lennoxsaint/eddy"
    assert manifest["interface"]["composerIcon"].endswith("eddy-eagle-icon.png")
    assert manifest["interface"]["logo"].endswith("eddy-eagle-logo.png")
    assert mcp["mcpServers"]["eddy"]["args"] == ["./scripts/eddy_plugin_mcp.py"]


def test_bootstrap_tracks_stable_tags_and_dry_run_does_not_mutate(tmp_path: Path) -> None:
    bootstrap = load_bootstrap()

    result = bootstrap.ensure_latest_stable(home=tmp_path, dry_run=True, tag="v3.0.0")

    assert result["status"] == "would_update"
    assert result["latest_tag"] == "v3.0.0"
    assert result["mutated"] is False
    assert not (tmp_path / "plugin-state.json").exists()


def test_plugin_install_is_not_editable_before_atomic_move() -> None:
    bootstrap = BOOTSTRAP.read_text()

    assert '"-e", f"{candidate_source}[mcp]"' not in bootstrap
    assert '"pip", "install", f"{candidate_source}[mcp]"' in bootstrap
    assert "stable_tag_commit_mismatch" in bootstrap
    assert "stable_tag_moved" in bootstrap
    assert "active_commit" in bootstrap


def test_plugin_uses_healthy_active_install_when_tag_lookup_is_offline(
    tmp_path: Path, monkeypatch
) -> None:
    bootstrap = load_bootstrap()
    bootstrap.write_state({"active_tag": "v3.0.0", "status": "active"}, tmp_path)
    monkeypatch.setattr(
        bootstrap,
        "latest_stable_tag",
        lambda repo_url: (_ for _ in ()).throw(RuntimeError("network_offline")),
    )
    monkeypatch.setattr(bootstrap, "active_install_healthy", lambda root: True)

    result = bootstrap.ensure_latest_stable(home=tmp_path)

    assert result["status"] == "offline_fallback"
    assert result["ok"] is True
    assert result["active_tag"] == "v3.0.0"


def test_plugin_prefers_verified_owner_channel_before_stable_tags(
    tmp_path: Path, monkeypatch
) -> None:
    bootstrap = load_bootstrap()
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    python = tmp_path / "python"
    python.write_text("executable")
    (tmp_path / "owner-channel.json").write_text(
        json.dumps({"canonical_root": str(canonical), "python": str(python)})
    )
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda *args, **kwargs: bootstrap.CommandResult([], 0, "3.0.0\n", ""),
    )
    monkeypatch.setattr(
        bootstrap,
        "latest_stable_tag",
        lambda repo_url: (_ for _ in ()).throw(AssertionError("stable lookup must not run")),
    )

    result = bootstrap.ensure_latest_stable(home=tmp_path)

    assert result["status"] == "owner_channel"
    assert result["python"] == str(python)
    assert result["canonical_root"] == str(canonical)
