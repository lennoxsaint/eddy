"""v1.4: JobManager — the subprocess job model behind the TUI + MCP server. Tested with an injected
spawn so no real `eddy` process launches: slug uniquification, the no-overwrite guard, status derived
from exit code + on-disk phase, and cancel semantics."""

from __future__ import annotations

import json

import pytest

from eddy.jobs import JobManager


class _Proc:
    def __init__(self, rc=None):
        self.pid = 7
        self._rc = rc
        self.terminated = False

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True


def _jm(tmp_path, procs):
    made: list = []

    def spawn(argv, log_path, env):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        p = procs[len(made)] if len(made) < len(procs) else _Proc(None)
        made.append(p)
        return p

    return JobManager(runs_dir=tmp_path, spawn=spawn)


def test_start_run_uses_deterministic_slug(tmp_path):
    jm = _jm(tmp_path, [_Proc(None)])
    job = jm.start_run("/x/myclip.mp4")
    assert "myclip" in job.id and job.kind == "run"
    assert job.run_dir == tmp_path / job.id


def test_free_slug_uniquifies_when_live(tmp_path):
    jm = _jm(tmp_path, [_Proc(None), _Proc(None)])
    a = jm.start_run("/x/clip.mp4")  # live (poll None)
    b = jm.start_run("/x/clip.mp4")  # same source must NOT reuse the live slug
    assert a.id != b.id and b.id.endswith("-2")


def test_launch_refuses_to_overwrite_a_live_job(tmp_path):
    jm = _jm(tmp_path, [_Proc(None)])
    rd = tmp_path / "ep1"
    rd.mkdir()
    jm.start_render(str(rd))  # id="ep1", live
    with pytest.raises(RuntimeError, match="already running"):
        jm.start_render(str(rd))  # same id, still live -> refuse (would orphan the first child)


def test_start_run_threads_focus_and_extract(tmp_path):
    jm = _jm(tmp_path, [_Proc(None)])
    job = jm.start_run("/x/clip.mp4", focus="only the codex bit", focus_mode="extract")
    assert "--focus" in job.argv
    assert job.argv[job.argv.index("--focus") + 1] == "only the codex bit"
    assert "--extract" in job.argv and "--no-extract" not in job.argv


def test_start_run_steer_passes_no_extract(tmp_path):
    jm = _jm(tmp_path, [_Proc(None)])
    job = jm.start_run("/x/clip.mp4", focus="center on pricing", focus_mode="steer")
    assert "--focus" in job.argv and "--no-extract" in job.argv


def test_start_run_without_focus_adds_no_focus_flags(tmp_path):
    jm = _jm(tmp_path, [_Proc(None)])
    job = jm.start_run("/x/clip.mp4")
    assert "--focus" not in job.argv and "--extract" not in job.argv and "--no-extract" not in job.argv


def test_start_run_threads_edit_path_and_fallback(tmp_path):
    jm = _jm(tmp_path, [_Proc(None)])
    job = jm.start_run("/x/clip.mp4", edit_path="claude_cli", auto_fallback=False)
    assert "--edit-path" in job.argv
    assert job.argv[job.argv.index("--edit-path") + 1] == "claude_cli"
    assert "--no-auto-fallback" in job.argv


def test_start_edit_threads_edit_path_and_fallback_policy(tmp_path):
    jm = _jm(tmp_path, [_Proc(None)])
    job = jm.start_edit(
        "/x/clip.mp4",
        edit_path="host_kernel",
        auto_fallback=False,
        fallback_policy="agent_subscription",
        motion_mode="required",
        audio_audition="required",
    )
    assert "--edit-path" in job.argv
    assert job.argv[job.argv.index("--edit-path") + 1] == "host_kernel"
    assert "--no-auto-fallback" in job.argv
    assert "--fallback-policy" in job.argv
    assert job.argv[job.argv.index("--motion-mode") + 1] == "required"
    assert job.argv[job.argv.index("--audio-audition") + 1] == "required"


def test_status_tracks_exit_code(tmp_path):
    p = _Proc(None)
    jm = _jm(tmp_path, [p])
    job = jm.start_run("/x/clip.mp4")
    assert jm.status(job.id)["state"] == "running"
    p._rc = 0
    assert jm.status(job.id)["state"] == "completed"
    p._rc = 1
    st = jm.status(job.id)
    assert st["state"] == "failed" and "log_tail" in st


def test_status_of_unknown_job_infers_from_disk(tmp_path):
    jm = _jm(tmp_path, [])
    (tmp_path / "done-run").mkdir()
    (tmp_path / "done-run" / "state.json").write_text(json.dumps({"phase": "done"}))
    assert jm.status("done-run")["state"] == "completed"
    (tmp_path / "wip-run").mkdir()
    (tmp_path / "wip-run" / "state.json").write_text(json.dumps({"phase": "final_render"}))
    assert jm.status("wip-run")["state"] == "interrupted"
    assert jm.status("ghost")["state"] == "unknown"


def test_cancel_terminates_live_then_reports_finished(tmp_path):
    p = _Proc(None)
    jm = _jm(tmp_path, [p])
    job = jm.start_run("/x/clip.mp4")
    assert jm.cancel(job.id) == {"job_id": job.id, "cancelled": True}
    assert p.terminated is True
    p._rc = 0  # now finished
    res = jm.cancel(job.id)
    assert res["cancelled"] is False and "finished" in res["reason"]
    assert jm.cancel("ghost")["cancelled"] is False
