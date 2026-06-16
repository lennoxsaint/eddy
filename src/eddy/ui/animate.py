"""The sprite animator — Eddy moves while long work runs.

`animate()` is a context manager that, on an interactive terminal, drives a multi-frame sprite +
status line through a Rich `Live` from a background thread (the main thread keeps doing the real
work and just calls `handle.update(...)`). When animation is gated off (piped output, CI, dumb
terminal, `EDDY_NO_ANIM`, or the MCP subprocess), it degrades to plain one-line status prints — no
sprite, no escape soup — so logs and machine readers stay clean.

The Live runs `transient=True`, so the animation clears on exit; callers print a durable final line
themselves (or pass `final_state` to stamp one).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import RenderableType
from rich.live import Live
from rich.table import Table
from rich.text import Text

from eddy.ui import console as ui


class AnimHandle:
    """Caller-facing control surface: update the status line and/or the sprite's emotional state.

    Thread-safe. In animated mode the background loop reads this; in static mode `update()` prints
    each distinct status line once so non-interactive consumers still see progress.
    """

    def __init__(self, *, animated: bool, state: str, status: str) -> None:
        self._lock = threading.Lock()
        self._animated = animated
        self.state = state
        self.status = status
        self._last_printed: str | None = None

    def update(self, status: str | None = None, state: str | None = None) -> None:
        with self._lock:
            if status is not None:
                self.status = status
            if state is not None:
                self.state = state
            line = self.status
            should_print = not self._animated and status is not None and line != self._last_printed
            if should_print:
                self._last_printed = line
        if should_print:
            ui.console().print(Text.from_markup(line) if line else Text(""))

    def snapshot(self) -> tuple[str, str]:
        with self._lock:
            return self.state, self.status


def _frame(handle: AnimHandle, index: int) -> RenderableType:
    state, status = handle.snapshot()
    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="center", vertical="middle")
    grid.add_column(vertical="middle")
    grid.add_row(ui.sprite_renderable(state, index, small=True), Text.from_markup(status) if status else Text(""))
    return grid


@contextmanager
def animate(
    status: str = "",
    state: str = "working",
    fps: float = 2.5,
    final_state: str | None = None,
) -> Iterator[AnimHandle]:
    """Animate the sprite for the duration of the block.

    `status` is the initial status line (Rich markup ok); update it via the yielded handle. `state`
    picks the sprite mood. On exit, if `final_state` is given and animation was live, a single durable
    sprite frame in that state is stamped so the terminal keeps a trace after the transient clear.
    """
    animated = ui.anim_enabled()
    handle = AnimHandle(animated=animated, state=state, status=status)

    if not animated:
        # static / non-interactive: emit the opening status line once, then just run the work.
        if status:
            ui.console().print(Text.from_markup(status))
            handle._last_printed = status
        yield handle
        return

    stop = threading.Event()
    console = ui.console()

    def _loop() -> None:
        index = 0
        with Live(_frame(handle, index), console=console, refresh_per_second=fps, transient=True, auto_refresh=False) as live:
            while not stop.is_set():
                live.update(_frame(handle, index))
                live.refresh()
                index += 1
                stop.wait(1.0 / fps)

    thread = threading.Thread(target=_loop, name="eddy-sprite", daemon=True)
    thread.start()
    try:
        yield handle
    finally:
        stop.set()
        thread.join(timeout=2.0)
        if final_state is not None:
            console.print(ui.sprite_renderable(final_state, small=True))
