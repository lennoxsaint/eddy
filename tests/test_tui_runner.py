"""The TUI data/runner layer: reads from disk, dispatches mutating intents through the (fake-spawned)
JobManager, and routes destructive intents to clean/purge."""

from __future__ import annotations

import json

from eddy.jobs import JobManager
from eddy.tui.intents import Intent
from eddy.tui.runner import TuiData


class _FakeProc:
    pid = 11

    def poll(self):
        return None


class _Cfg:
    class provider:
        active = "ollama"

    def __init__(self, runs_dir):
        self.runs_dir = runs_dir


def _data(tmp_path):
    def spawn(argv, log_path, env):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        return _FakeProc()

    return TuiData(jobs=JobManager(runs_dir=tmp_path, spawn=spawn), cfg=_Cfg(tmp_path))


def _make_run(tmp_path, slug, phase="done"):
    rd = tmp_path / slug
    (rd / "final").mkdir(parents=True)
    (rd / "manifest.json").write_text("{}")
    (rd / "state.json").write_text(json.dumps({"phase": phase, "attempts": [], "best_iter": 1}))
    return rd


def test_runs_newest_first(tmp_path):
    _make_run(tmp_path, "2026-a")
    _make_run(tmp_path, "2026-b")
    runs = _data(tmp_path).runs()
    assert [r["slug"] for r in runs] == ["2026-b", "2026-a"]


def test_run_detail_reads_state_and_artifacts(tmp_path):
    rd = _make_run(tmp_path, "demo", phase="final_render")
    (rd / "final" / "video.mp4").write_bytes(b"x")
    d = _data(tmp_path).run_detail("demo")
    assert d["state"]["phase"] == "final_render" and "video.mp4" in d["artifacts"]


def test_execute_run_starts_a_job(tmp_path):
    data = _data(tmp_path)
    res = data.execute(Intent(action="run", args={"source": "~/x.mp4"}, needs_confirm=True))
    assert res["kind"] == "job" and res["job_id"]
    assert data.any_running() is True


def test_execute_clean_calls_clean_run(tmp_path, monkeypatch):
    called = {}
    monkeypatch.setattr("eddy.clean.clean_run", lambda rd, **k: called.setdefault("rd", rd))
    _data(tmp_path).execute(Intent(action="clean", args={"run": "demo"}, needs_confirm=True))
    assert "demo" in str(called["rd"])


def test_execute_purge_passes_full(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr("eddy.clean.purge_run", lambda rd, full=False, **k: seen.update(full=full))
    _data(tmp_path).execute(Intent(action="purge", args={"run": "demo", "full": True}, needs_confirm=True))
    assert seen["full"] is True


def test_brain_label(tmp_path):
    assert "ollama" in _data(tmp_path).brain_label()


def test_run_verdict_speaks_in_passes_not_floats():
    from eddy.tui.runner import run_verdict

    assert run_verdict({"phase": "done", "attempts": [{}, {}, {}]}) == "Kept the best of 3 editing passes."
    assert run_verdict({"phase": "done", "attempts": [{}]}) == "Edited in a single clean pass."
    assert run_verdict({"attempts": []}) is None
    mid = run_verdict({"phase": "iteration_2", "attempts": [{"iteration": 2, "gates_passed": False}]})
    assert "pass 2" in mid and "refining" in mid


def test_log_tail_reads_job_log(tmp_path):
    data = _data(tmp_path)
    job = data.jobs.start_run("~/x.mp4")  # fake spawn wrote an empty log
    job.log_path.write_text("line1\nline2\nlast line\n")
    assert "last line" in data.log_tail(job.id)


def test_cancel_delegates_to_jobmanager(tmp_path):
    data = _data(tmp_path)
    job = data.jobs.start_run("~/x.mp4")
    terminated = {}
    job.proc.terminate = lambda: terminated.setdefault("hit", True)  # _FakeProc.poll() is None (running)
    res = data.cancel(job.id)
    assert res["job_id"] == job.id and res["cancelled"] is True and terminated["hit"]


def test_failed_jobs_lists_nonzero_exits(tmp_path):
    data = _data(tmp_path)
    job = data.jobs.start_run("~/x.mp4")
    job.proc.poll = lambda: 1  # pretend the child exited non-zero
    assert [j["job_id"] for j in data.failed_jobs()] == [job.id]


def test_is_interrupted_for_unfinished_untracked_run(tmp_path):
    _make_run(tmp_path, "wip", phase="final_render")  # progress on disk, no live job
    _make_run(tmp_path, "fin", phase="done")
    data = _data(tmp_path)
    assert data.is_interrupted("wip") is True
    assert data.is_interrupted("fin") is False


def test_reveal_opens_existing_results(tmp_path, monkeypatch):
    import eddy.tui.runner as runner_mod

    _make_run(tmp_path, "demo")  # creates demo/final
    seen: dict = {}
    monkeypatch.setattr(runner_mod.sys, "platform", "linux")
    monkeypatch.setattr(runner_mod.shutil, "which", lambda n: "/usr/bin/xdg-open")
    monkeypatch.setattr(runner_mod.subprocess, "Popen", lambda argv, **k: seen.setdefault("argv", argv))
    assert _data(tmp_path).reveal("demo") is True
    assert "final" in str(seen["argv"][-1])


def test_reveal_missing_run_returns_false(tmp_path):
    assert _data(tmp_path).reveal("nope") is False


def test_local_provider_pins_to_ollama(monkeypatch):
    # NL interpretation must use the LOCAL brain, never the (possibly cloud) active provider.
    seen = {}

    def fake_get_provider(cfg, name=None, receipts=None):
        seen["name"] = name
        return object()

    monkeypatch.setattr("eddy.providers.base.get_provider", fake_get_provider)
    from eddy.tui.runner import local_provider

    assert local_provider() is not None
    assert seen["name"] == "ollama"
