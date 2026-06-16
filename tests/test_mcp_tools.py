"""The MCP tool functions: reads return structured data, stdout is protected, destructive ops refuse
without confirm, and job wrappers delegate to the (fake-spawned) manager."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.mcp_server import tools
from eddy.mcp_server.jobs import JobManager


class _FakeCfg:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.profiles: dict = {}


class _FakeProc:
    pid = 99

    def poll(self):
        return None


def _point_runs_at(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "load_config", lambda path=None: _FakeCfg(tmp_path))


def _make_run(tmp_path, slug="2026-demo", phase="done"):
    rd = tmp_path / slug
    (rd / "final").mkdir(parents=True)
    (rd / "manifest.json").write_text("{}")  # list_runs requires this marker
    (rd / "state.json").write_text(json.dumps({"phase": phase, "best_iter": 3}))
    return rd


def test_resolve_run_slug_vs_path(monkeypatch, tmp_path):
    _point_runs_at(monkeypatch, tmp_path)
    rd = _make_run(tmp_path)
    assert tools._resolve_run("2026-demo") == rd  # bare slug
    assert tools._resolve_run(str(rd)) == rd  # explicit path


def test_quiet_suppresses_stdout(capsys):
    with tools._quiet():
        print("should not reach stdout")
    assert capsys.readouterr().out == ""


def test_eddy_runs_lists_runs(monkeypatch, tmp_path):
    _point_runs_at(monkeypatch, tmp_path)
    _make_run(tmp_path, "2026-a", "done")
    _make_run(tmp_path, "2026-b", "iteration_1")
    out = tools.eddy_runs()
    assert out["count"] == 2
    assert {r["slug"] for r in out["runs"]} == {"2026-a", "2026-b"}


def test_eddy_run_inspect(monkeypatch, tmp_path):
    _point_runs_at(monkeypatch, tmp_path)
    rd = _make_run(tmp_path)
    (rd / "final" / "video.mp4").write_bytes(b"x")
    out = tools.eddy_run_inspect("2026-demo")
    assert out["slug"] == "2026-demo" and out["state"]["phase"] == "done"
    assert "video.mp4" in out["final_artifacts"]


def test_eddy_artifacts_reads_text_and_lists_videos(monkeypatch, tmp_path):
    _point_runs_at(monkeypatch, tmp_path)
    rd = _make_run(tmp_path)
    (rd / "final" / "titles.json").write_text(json.dumps([{"title": "Hi"}]))
    (rd / "final" / "description.md").write_text("the description")
    (rd / "final" / "video.mp4").write_bytes(b"012345")
    out = tools.eddy_artifacts("2026-demo")
    assert out["titles"][0]["title"] == "Hi"
    assert out["description"] == "the description"
    assert out["videos"][0]["name"] == "video.mp4" and out["videos"][0]["bytes"] == 6


def test_clean_and_purge_refuse_without_confirm(monkeypatch, tmp_path):
    _point_runs_at(monkeypatch, tmp_path)
    assert tools.eddy_clean("2026-demo")["refused"] is True
    assert tools.eddy_purge("2026-demo")["refused"] is True


def test_job_wrappers_delegate(monkeypatch, tmp_path):
    captured: dict = {}

    def spawn(argv, log_path, env):
        captured["argv"] = argv
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        return _FakeProc()

    monkeypatch.setattr(tools, "_jobs", JobManager(runs_dir=tmp_path, spawn=spawn))
    out = tools.eddy_run_start("/foot.mp4", slug="myslug")
    assert out["job_id"] == "myslug"
    assert out["run_dir"] == str(tmp_path / "myslug")
    assert "run" in captured["argv"]
    # status flows back through the same manager
    assert tools.eddy_job_status("myslug")["state"] == "running"


def test_eddy_doctor_returns_detect_and_preflight():
    out = tools.eddy_doctor()
    assert "detect" in out and "preflight" in out
    assert isinstance(out["preflight"], list)
