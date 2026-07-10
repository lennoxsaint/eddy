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
    assert mcp["mcpServers"]["eddy"]["args"] == ["./scripts/eddy_plugin_mcp.py"]


def test_bootstrap_tracks_stable_tags_and_dry_run_does_not_mutate(tmp_path: Path) -> None:
    bootstrap = load_bootstrap()

    result = bootstrap.ensure_latest_stable(home=tmp_path, dry_run=True, tag="v3.0.0")

    assert result["status"] == "would_update"
    assert result["latest_tag"] == "v3.0.0"
    assert result["mutated"] is False
    assert not (tmp_path / "plugin-state.json").exists()
