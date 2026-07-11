from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ship_to_github.py"


def _shipping():
    spec = importlib.util.spec_from_file_location("eddy_shipping_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_guarded_ship_rejects_unintended_and_private_changes() -> None:
    shipping = _shipping()

    with pytest.raises(RuntimeError, match="ship_unintended_changes"):
        shipping.validate_allowlist({"src/eddy/new.py", "notes.txt"}, {"src/eddy/new.py"})
    with pytest.raises(RuntimeError, match="ship_private_run_artifacts"):
        shipping.validate_allowlist({"proof/final.mp4"}, {"proof/final.mp4"})


def test_guarded_ship_allows_generated_projections_without_manual_listing() -> None:
    shipping = _shipping()

    shipping.validate_allowlist(
        {
            "src/eddy/new.py",
            "plugins/eddy/skills/eddy/SKILL.md",
            "integrations/claude-code/skills/eddy/SKILL.md",
        },
        {"src/eddy/new.py"},
    )
