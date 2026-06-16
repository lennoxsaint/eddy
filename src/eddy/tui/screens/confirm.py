"""A confirm modal — used for destructive ops AND for confirming an NL-interpreted action, so Eddy
never acts on a guessed intent (or deletes anything) without a yes."""

from __future__ import annotations

from rich.markup import escape
from textual import on
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [("y", "confirm", "Yes"), ("n", "cancel", "No"), ("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, title: str = "Confirm") -> None:
        super().__init__()
        self._prompt = prompt
        self._title = title

    def compose(self):
        with Vertical(id="dialog"):
            yield Static(f"[#f5b836 bold]{escape(self._title)}[/]\n\n{escape(self._prompt)}", id="dtext")
            with Horizontal(id="dbtns"):
                yield Button("Confirm", variant="warning", id="yes")
                yield Button("Cancel", id="no")
        yield Footer()

    @on(Button.Pressed, "#yes")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def _no(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
