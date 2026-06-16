"""The sprite animator. In tests (no real TTY) it takes the static path: no background thread, no
Live, just clean status lines — exactly what the MCP subprocess and CI get."""

from __future__ import annotations

import io

from rich.console import Console

from eddy.ui import console as ui
from eddy.ui.animate import AnimHandle, animate


def teardown_function() -> None:
    ui.reset()


def _capture() -> io.StringIO:
    buf = io.StringIO()
    ui._console = Console(file=buf, force_terminal=False, theme=ui._THEME, width=100)
    return buf


def test_static_path_prints_initial_status_once():
    buf = _capture()
    with animate(status="transcribing", state="working") as h:
        assert isinstance(h, AnimHandle)
    assert buf.getvalue().count("transcribing") == 1


def test_static_handle_prints_distinct_updates_not_duplicates():
    buf = _capture()
    with animate(status="step 1") as h:
        h.update(status="step 2")
        h.update(status="step 2")  # duplicate suppressed
        h.update(status="step 3")
    out = buf.getvalue()
    assert out.count("step 2") == 1 and "step 3" in out


def test_handle_snapshot_tracks_state():
    h = AnimHandle(animated=False, state="working", status="x")
    h.update(state="success")
    assert h.snapshot()[0] == "success"


def test_animated_handle_does_not_print_inline(monkeypatch):
    # when 'animated', update() must not emit lines (the Live owns the display)
    buf = _capture()
    h = AnimHandle(animated=True, state="working", status="")
    h.update(status="hello")
    assert "hello" not in buf.getvalue()
