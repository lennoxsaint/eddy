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


async def test_empty_state_when_no_runs(tmp_path):
    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        scr = app.screen
        assert scr.query_one("#runsempty", Static).display is True
        assert scr.query_one("#runs", DataTable).display is False


async def test_failed_run_shows_error_eaglet(tmp_path):
    app, data = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        job = data.jobs.start_run("~/x.mp4")
        job.proc.poll = lambda: 1  # the child exited non-zero → failed
        scr = app.screen
        scr._was_running = True  # we'd seen it running, now it's finishing
        scr._poll()
        await pilot.pause()
        assert scr.query_one("#eagle", EagleWidget).state == "error"  # NOT the happy bird


async def test_suggester_completes_verb_path_and_slug(tmp_path):
    from eddy.tui.screens.home import _CmdSuggester

    (tmp_path / "Movies").mkdir()
    sug = _CmdSuggester(lambda: ["2026-demo"])
    assert await sug.get_suggestion("ru") == "run"
    assert await sug.get_suggestion("open 2026") == "open 2026-demo"
    assert await sug.get_suggestion(f"run {tmp_path}/Mov") == f"run {tmp_path}/Movies/"


async def test_preview_modal_opens_for_selected_run(tmp_path):
    from eddy.tui.screens.preview import PreviewScreen

    final = tmp_path / "2026-demo" / "final"
    final.mkdir(parents=True)
    (final / "titles.md").write_text("# Title candidates\n1. Hello world")
    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        scr = app.screen
        scr._selected = "2026-demo"
        scr.action_preview()
        await pilot.pause()
        assert isinstance(app.screen, PreviewScreen)
        assert app.screen._items  # found the artifact


async def test_why_failed_modal_opens_for_failed_run(tmp_path):
    from eddy.tui.screens.failure import FailureScreen

    log = tmp_path / ".mcp-jobs" / "2026-boom.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("✗ Media error: boom\n  → Make sure ffmpeg 8+ is installed (run `eddy doctor`).\n")
    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        scr = app.screen
        scr._selected = "2026-boom"
        scr.action_why_failed()
        await pilot.pause()
        assert isinstance(app.screen, FailureScreen)
        assert "Media error" in app.screen._d["headline"]


async def test_focused_run_opens_output_chooser_then_starts_job(tmp_path):
    from eddy.tui.screens.output import OutputScreen

    app, data = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.screen.query_one("#cmd", Input).value = (
            "edit this video: ~/codex.mp4 - only keep my Codex explanation"
        )
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, OutputScreen)  # a focused edit asks what to PRODUCE
        await pilot.press("v")  # just the video
        await pilot.pause()
        await pilot.pause()
        assert data.jobs.list(), "picking an output should start the job"
        argv = list(data.jobs._jobs.values())[0].argv
        assert "--focus" in argv and "--extract" in argv
        assert "--skip-shorts" in argv and "--skip-package" in argv  # 'video' = skip both


async def test_focused_run_cancel_starts_nothing(tmp_path):
    from eddy.tui.screens.output import OutputScreen

    app, data = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.screen.query_one("#cmd", Input).value = "edit ~/codex.mp4 - only the demo"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, OutputScreen)
        await pilot.press("escape")  # cancel the chooser
        await pilot.pause()
        assert not data.jobs.list()


async def test_plain_run_still_uses_yes_no_confirm(tmp_path):
    # a run WITHOUT a focus brief keeps the original confirm path (not the output chooser)
    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        app.screen.query_one("#cmd", Input).value = "run ~/clip.mp4"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)


@pytest.mark.parametrize("state", ["idle", "working", "success", "error"])
async def test_eagle_state_can_change(tmp_path, state):
    app, _ = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        eagle = app.screen.query_one("#eagle", EagleWidget)
        eagle.set_state(state)
        assert eagle.state == state
