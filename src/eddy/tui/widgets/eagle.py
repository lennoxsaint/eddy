"""The animated chibi-eaglet widget for the TUI header.

Renders the pixel sprite (via `pixels.to_text`, which carries explicit truecolor so it needs no theme)
by overriding `render()`, and advances frames on a timer — so Eddy blinks while idle and reacts to app
activity. `set_state` swaps the mood (idle / thinking / working / success / error). On a terminal that
can't do colour (half-blocks are unreadable below 256 colours) it falls back to the plain-ASCII eaglet.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from eddy.ui import pixels, sprite


def needs_ascii(color_system: str | None) -> bool:
    """Half-block pixels need at least 256 colours to read — fall back to ASCII below that."""
    return color_system in (None, "standard")


class EagleWidget(Static):
    def __init__(self, small: bool = True, state: str = "idle", **kwargs) -> None:
        super().__init__(**kwargs)
        self._small = small
        self._state = state
        self._frame = 0

    def render(self) -> Text:
        try:
            color_system = self.app.console.color_system
        except Exception:
            color_system = "truecolor"  # no running app (unit test) — keep the pixel art
        if needs_ascii(color_system):
            return Text(sprite.ascii_art())
        return pixels.to_text(sprite.frame(self._state, self._frame, small=self._small))

    def on_mount(self) -> None:
        self.set_interval(0.7, self._tick)  # gentle blink / flap cadence

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self._frame = 0
            self.refresh()

    @property
    def state(self) -> str:
        return self._state

    def _tick(self) -> None:
        self._frame += 1
        self.refresh()
