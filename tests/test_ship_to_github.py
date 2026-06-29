from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ship_to_github", ROOT / "scripts" / "ship_to_github.py")
assert SPEC and SPEC.loader
ship = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ship)


def test_tag_must_match_project_version():
    assert ship.tag_matches_version("v1.10.5", "1.10.5") is True
    assert ship.tag_matches_version("1.10.5", "1.10.5") is False
    assert ship.tag_matches_version("v1.10.2", "1.10.5") is False


def test_run_artifact_detection_is_conservative():
    assert ship.is_run_artifact("runs/demo/final/video.mp4") is True
    assert ship.is_run_artifact("work/scratch.txt") is True
    assert ship.is_run_artifact("src/eddy/runs.py") is False
    assert ship.is_run_artifact("docs/decision-log.md") is False
