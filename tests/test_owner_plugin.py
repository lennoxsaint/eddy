from __future__ import annotations

import json
import shutil
from pathlib import Path

from eddy import owner_plugin


def test_owner_plugin_status_detects_cache_and_marketplace_drift(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    canonical = tmp_path / "canonical"
    plugin = canonical / "plugins" / "eddy"
    plugin.mkdir(parents=True)
    (plugin / "plugin.txt").write_text("v3")
    marketplace = home / ".agents" / "plugins" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "name": "eddy",
                        "source": {"source": "local", "path": "./plugins/eddy"},
                    }
                ]
            }
        )
    )
    owner_source = home / "plugins" / "eddy"
    owner_source.parent.mkdir(parents=True)
    owner_source.symlink_to(plugin, target_is_directory=True)
    cache = home / ".codex" / "plugins" / "cache" / "personal" / "eddy" / "3.0.0"
    shutil.copytree(plugin, cache)
    monkeypatch.setattr(owner_plugin.Path, "home", lambda: home)
    monkeypatch.setattr(owner_plugin, "_app_server_probe", lambda root: {"ok": True})

    green = owner_plugin.owner_plugin_status(canonical)
    (cache / "plugin.txt").write_text("stale")
    stale = owner_plugin.owner_plugin_status(canonical)

    assert green["ok"] is True
    assert stale["ok"] is False
    assert stale["cache_ok"] is False
