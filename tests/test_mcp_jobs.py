"""The subprocess job manager: argv construction, status from exit-code + on-disk phase, cancel.
A fake spawn keeps it hermetic — no real `eddy` process is launched."""

from __future__ import annotations

import json

from eddy.mcp_server.jobs import JobManager


class FakeProc:
    def __init__(self, rc: int | None = None) -> None:
        self._rc = rc
        self.pid = 4242
        self.terminated = False

    def poll(self) -> int | None:
        return self._rc

    def terminate(self) -> None:
        self.terminated = True
        self._rc = -15


def _mgr(tmp_path, rc=None, capture=None):
    def spawn(argv, log_path, env):
        if capture is not None:
            capture["argv"] = argv
            capture["env"] = env
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("starting…\nboom: it broke\n")
        return FakeProc(rc)

    return JobManager(runs_dir=tmp_path, spawn=spawn)


def test_start_run_builds_argv_and_run_dir(tmp_path):
    cap: dict = {}
    job = _mgr(tmp_path, capture=cap).start_run("/foot/age.mp4", slug="myslug", target_minutes=8.0, local_only=True)
    assert job.id == "myslug"
    assert job.run_dir == tmp_path / "myslug"
    assert cap["argv"][1:4] == ["-m", "eddy", "run"]
    assert "--slug" in cap["argv"] and "myslug" in cap["argv"]
    assert "--local-only" in cap["argv"] and "--target-minutes" in cap["argv"]
    assert cap["env"]["EDDY_NO_ANIM"] == "1"  # child must not animate


def test_three_state_skip_flags(tmp_path):
    cap: dict = {}
    _mgr(tmp_path, capture=cap).start_run("/x.mp4", slug="s", skip_shorts=True, skip_package=False)
    assert "--skip-shorts" in cap["argv"]
    assert "--no-skip-package" in cap["argv"]


def test_status_running_completed_failed(tmp_path):
    mgr = _mgr(tmp_path, rc=None)
    mgr.start_run("/x.mp4", slug="s")
    assert mgr.status("s")["state"] == "running"

    mgr2 = _mgr(tmp_path, rc=0)
    (tmp_path / "s2").mkdir()
    (tmp_path / "s2" / "state.json").write_text(json.dumps({"phase": "done"}))
    mgr2.start_run("/x.mp4", slug="s2")
    st = mgr2.status("s2")
    assert st["state"] == "completed" and st["phase"] == "done"

    mgr3 = _mgr(tmp_path, rc=1)
    mgr3.start_run("/x.mp4", slug="s3")
    failed = mgr3.status("s3")
    assert failed["state"] == "failed" and "boom" in failed["log_tail"]


def test_cancel_terminates(tmp_path):
    mgr = _mgr(tmp_path, rc=None)
    job = mgr.start_run("/x.mp4", slug="s")
    out = mgr.cancel("s")
    assert out["cancelled"] is True and job.proc.terminated is True


def test_unknown_job_inferred_from_disk(tmp_path):
    mgr = _mgr(tmp_path)
    # a job this server never started, but whose run dir exists on disk
    (tmp_path / "ghost").mkdir()
    (tmp_path / "ghost" / "state.json").write_text(json.dumps({"phase": "iteration_2"}))
    st = mgr.status("ghost")
    assert st["state"] == "interrupted" and st["phase"] == "iteration_2"
    assert mgr.status("nope")["state"] == "unknown"


def test_render_job_uses_run_dir_name_as_id(tmp_path):
    cap: dict = {}
    job = _mgr(tmp_path, capture=cap).start_render(str(tmp_path / "somerun"), proxy=True)
    assert job.id == "somerun" and "--proxy" in cap["argv"]


def test_same_source_double_start_uniquifies_slug(tmp_path):
    # two live runs of the same source must NOT share a run dir (would corrupt state.json)
    mgr = _mgr(tmp_path, rc=None)  # both stay 'running'
    a = mgr.start_run("/foot/age.mp4")
    b = mgr.start_run("/foot/age.mp4")
    assert a.id != b.id and b.id == f"{a.id}-2"
    assert a.run_dir != b.run_dir


def test_launch_refuses_live_duplicate(tmp_path):
    import pytest

    mgr = _mgr(tmp_path, rc=None)
    mgr.start_render(str(tmp_path / "run1"))
    with pytest.raises(RuntimeError, match="already running"):
        mgr.start_render(str(tmp_path / "run1"))  # same run, still rendering


def test_finished_job_can_restart_same_slug(tmp_path):
    mgr = _mgr(tmp_path, rc=0)  # finishes immediately
    mgr.start_render(str(tmp_path / "run1"))
    mgr.start_render(str(tmp_path / "run1"))  # prior finished -> allowed, no raise
