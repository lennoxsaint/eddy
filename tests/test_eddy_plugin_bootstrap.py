import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "plugins" / "eddy" / "scripts" / "eddy_plugin_bootstrap.py"


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("eddy_plugin_bootstrap_for_test", BOOTSTRAP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_select_latest_stable_tag_ignores_prerelease_and_nonsemver():
    boot = load_bootstrap()
    payload = "\n".join(
        [
            "aaa\trefs/tags/v1.9.1",
            "bbb\trefs/tags/v1.10.1",
            "ccc\trefs/tags/v1.10.1-rc1",
            "ddd\trefs/tags/test",
        ]
    )
    assert boot.select_latest_stable_tag(payload) == "v1.10.1"


def test_bootstrap_dry_run_does_not_mutate(tmp_path, monkeypatch):
    boot = load_bootstrap()
    monkeypatch.setattr(boot, "latest_stable_tag", lambda repo_url: "v1.10.1")

    result = boot.ensure_latest_stable(home=tmp_path, dry_run=True, skip_studio_sound=True)

    assert result["status"] == "would_update"
    assert result["latest_tag"] == "v1.10.1"
    assert result["mutated"] is False
    assert result["skip_studio_sound"] is True
    assert not (tmp_path / "source").exists()
    assert not (tmp_path / "plugin-state.json").exists()
