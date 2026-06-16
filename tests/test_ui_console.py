"""The shared console: colour/animation gating and the brand surfaces. The gating is what keeps the
sprite off pipes, CI, and the MCP subprocess, so it's tested directly."""

from __future__ import annotations

import io

from rich.console import Console

from eddy.ui import console as ui


class _FakeTTY(io.StringIO):
    def isatty(self) -> bool:  # noqa: D401 - mimic a real terminal stream
        return True


def _capture() -> io.StringIO:
    """Install a forced-terminal capture console and return its buffer."""
    buf = io.StringIO()
    ui._console = Console(file=buf, force_terminal=True, color_system="truecolor", theme=ui._THEME, width=100)
    return buf


def teardown_function() -> None:
    ui.reset()


def test_color_disabled_without_terminal():
    ui._console = Console(file=io.StringIO(), force_terminal=False)
    assert ui.color_enabled() is False


def test_color_disabled_by_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    _capture()
    assert ui.color_enabled() is False


def test_anim_requires_tty_and_color(monkeypatch):
    monkeypatch.delenv("EDDY_NO_ANIM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("eddy.ui.console.sys.stdout", _FakeTTY())
    _capture()  # forced-terminal colour console
    assert ui.anim_enabled() is True
    monkeypatch.setenv("EDDY_NO_ANIM", "1")
    assert ui.anim_enabled() is False  # opt-out wins


def test_anim_off_when_not_a_tty():
    _capture()  # colour on, but stdout in pytest is not a real tty
    assert ui.anim_enabled() is False


def test_sprite_falls_back_to_ascii_without_colour():
    ui._console = Console(file=io.StringIO(), force_terminal=False)
    rendered = ui.sprite_renderable("idle").plain
    assert "(" in rendered and "▀" not in rendered  # ASCII eagle, not half-blocks


def test_sprite_uses_halfblocks_with_colour(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    _capture()
    assert "▀" in ui.sprite_renderable("idle").plain


def test_wake_screen_has_brand_and_hints():
    buf = _capture()
    ui.console().print(ui.wake_screen(runs=[{"slug": "demo", "phase": "done"}]))
    out = buf.getvalue()
    assert "EDDY" in out
    assert "eddy run" in out and "every command" in out
    assert "demo" in out  # fleet line


def test_status_helpers_render():
    buf = _capture()
    ui.ok("done")
    ui.warn("hmm")
    ui.err("nope")
    ui.note("fyi")
    ui.console().print(ui.banner("editing"))
    out = buf.getvalue()
    assert "done" in out and "hmm" in out and "nope" in out and "EDDY" in out
