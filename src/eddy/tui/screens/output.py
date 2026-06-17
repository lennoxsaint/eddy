"""The 'what should Eddy make?' chooser shown before a focused / extract edit. Lennox wants to pick
the output scope each time rather than have it hardcoded, so this doubles as the confirm step:
picking an option starts the run; Cancel/escape aborts. Returns 'video' | 'shorts' | 'kit' | None."""

from __future__ import annotations

from rich.markup import escape
from textual import on
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static

# choice -> (skip_shorts, skip_package)
OUTPUT_FLAGS: dict[str, tuple[bool, bool]] = {
    "video": (True, True),    # just the edited long video
    "shorts": (False, True),  # video + shorts, no launch-kit package
    "kit": (False, False),    # full launch kit (titles/thumbnails/newsletter + shorts)
}


class OutputScreen(ModalScreen[str | None]):
    BINDINGS = [
        ("v", "pick('video')", "Video"),
        ("s", "pick('shorts')", "+ Shorts"),
        ("k", "pick('kit')", "Full kit"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, summary: str) -> None:
        super().__init__()
        self._summary = summary

    def compose(self):
        with Vertical(id="dialog"):
            yield Static(
                f"[#f5b836 bold]What should Eddy make?[/]\n\n{escape(self._summary)}\n\n"
                "[#8b93a1]v[/] just the video   "
                "[#8b93a1]s[/] video + Shorts   "
                "[#8b93a1]k[/] full launch kit",
                id="dtext",
            )
            with Horizontal(id="dbtns"):
                yield Button("Video", variant="primary", id="video")
                yield Button("+ Shorts", id="shorts")
                yield Button("Full kit", id="kit")
                yield Button("Cancel", id="cancel")
        yield Footer()

    @on(Button.Pressed, "#video")
    def _v(self) -> None:
        self.dismiss("video")

    @on(Button.Pressed, "#shorts")
    def _s(self) -> None:
        self.dismiss("shorts")

    @on(Button.Pressed, "#kit")
    def _k(self) -> None:
        self.dismiss("kit")

    @on(Button.Pressed, "#cancel")
    def _c(self) -> None:
        self.dismiss(None)

    def action_pick(self, which: str) -> None:
        self.dismiss(which)

    def action_cancel(self) -> None:
        self.dismiss(None)
