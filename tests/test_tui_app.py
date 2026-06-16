"""The Eddy TUI end to end via Textual's pilot harness: mount, the command→confirm→job flow, the
doctor modal, and quit. The JobManager is fake-spawned so no real `eddy` process launches."""

from __future__ import annotations

import pytest
from textual.widgets import DataTable, Input, Static

from eddy.jobs import JobManager
from eddy.tui.app import EddyApp
from eddy.tui.runner import TuiData
from eddy.tui.screens.confirm import ConfirmScreen
from eddy.tui.widgets.eagle import EagleWidget


class _FakeProc:
    pid = 5

    def poll(self):
        return None


class _Cfg:
    class provider:
        active = "ollama"

    def __init__(self, runs_dir):
        self.runs_dir = runs_dir


def _app(tmp_path):
    def spawn(argv, log_path, env):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        return _FakeProc()

    data = TuiData(jobs=JobManager(runs_dir=tmp_path, spawn=spawn), cfg=_Cfg(tmp_path))
    return EddyApp(data=data), data


async def test_mounts_with_core_widgets(tmp_path):
    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        scr = app.screen
        assert scr.query_one("#eagle", EagleWidget)
        assert scr.query_one("#runs", DataTable)
        assert scr.query_one("#cmd", Input)
        assert scr.query_one("#monitor", Static)


async def test_run_command_confirms_then_starts_job(tmp_path):
    app, data = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.screen.query_one("#cmd", Input).value = "run ~/clip.mp4"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)  # destructive/long → confirm first
        await pilot.press("y")
        await pilot.pause()
        await pilot.pause()
        assert data.jobs.list(), "a job should have started after confirming"


async def test_cancel_confirm_starts_nothing(tmp_path):
    app, data = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.screen.query_one("#cmd", Input).value = "run ~/clip.mp4"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")  # cancel
        await pilot.pause()
        assert not data.jobs.list()


async def test_doctor_command_opens_modal(tmp_path):
    from eddy.tui.screens.doctor import DoctorScreen

    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.screen.query_one("#cmd", Input).value = "doctor"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DoctorScreen)


async def test_quit_command_exits(tmp_path):
    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.screen.query_one("#cmd", Input).value = "/quit"
        await pilot.press("enter")
        await pilot.pause()
    assert app._return_value is None  # app exited cleanly


@pytest.mark.parametrize("state", ["idle", "working", "success", "error"])
async def test_eagle_state_can_change(tmp_path, state):
    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        eagle = app.screen.query_one("#eagle", EagleWidget)
        eagle.set_state(state)
        assert eagle.state == state
