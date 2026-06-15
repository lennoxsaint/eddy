"""v0.4: open_run is bound to its exact footage. A slug collision must NEVER reuse a run dir
for different source video (that silently edited the wrong footage), and --resume must require
an existing run.
"""

import json

import pytest

from eddy.config import load_config
from eddy.runs import SourceError, open_run, sha256_file


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    cfg = load_config()
    cfg.paths.runs_dir = str(tmp_path / "runs")  # runs_dir is a derived property over paths.runs_dir
    monkeypatch.setattr("eddy.runs.load_config", lambda: cfg)
    return cfg.runs_dir


def _vid(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_open_creates_manifest_with_source_hash(tmp_path, runs_dir):
    v = _vid(tmp_path / "a" / "camera.mp4", b"AAAA")
    rd = open_run(v, slug="s1")
    m = json.loads((rd / "manifest.json").read_text())
    assert m["source_sha256"]["camera"] == sha256_file(v)


def test_reopen_same_footage_reuses_dir(tmp_path, runs_dir):
    v = _vid(tmp_path / "a" / "camera.mp4", b"AAAA")
    assert open_run(v, slug="s1") == open_run(v, slug="s1")


def test_slug_collision_with_different_footage_raises(tmp_path, runs_dir):
    a = _vid(tmp_path / "a" / "camera.mp4", b"AAAA")
    b = _vid(tmp_path / "b" / "camera.mp4", b"BBBB")
    open_run(a, slug="dup")
    with pytest.raises(SourceError, match="DIFFERENT source footage"):
        open_run(b, slug="dup")


def test_resume_without_existing_run_raises(tmp_path, runs_dir):
    v = _vid(tmp_path / "a" / "camera.mp4", b"AAAA")
    with pytest.raises(SourceError, match="nothing to resume"):
        open_run(v, slug="ghost", resume=True)


def test_resume_existing_same_footage_ok(tmp_path, runs_dir):
    v = _vid(tmp_path / "a" / "camera.mp4", b"AAAA")
    open_run(v, slug="s1")
    assert open_run(v, slug="s1", resume=True).name == "s1"
