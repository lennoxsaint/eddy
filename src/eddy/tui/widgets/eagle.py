"""The animated chibi-eaglet widget for the TUI header.

Renders the pixel sprite (via `pixels.to_text`, which carries explicit truecolor so it needs no theme)
by overriding `render()`, and advances frames on a timer — so Eddy blinks while idle and reacts to app
activity. `set_state` swaps the mood (idle / thinking / working / success / error).
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from eddy.ui import pixels, sprite


class EagleWidget(Static):
    def __init__(self, small: bool = True, state: str = "idle", **kwargs) -> None:
        super().__init__(**kwargs)
        self._small = small
        self._state = state
        self._frame = 0

    def render(self) -> Text:
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
