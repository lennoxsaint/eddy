"""A modal that explains a failed run in plain language: the friendly headline + concrete next step
(the same mapping errors.friendly_error produces), the crash-log path, and the tail of the run's log.

The point is that a non-technical creator gets an actionable answer *in the app* instead of a sad
eaglet and a log line they then have to go read a crash file to understand."""

from __future__ import annotations

from rich.markup import escape
from textual import on
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static

_GOLD = "#f5b836"
_DIM = "#8b909b"


class FailureScreen(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, detail: dict) -> None:
        super().__init__()
        self._d = detail

    def compose(self):
        d = self._d
        head = [
            f"[red bold]✗ {escape(str(d.get('slug', '')))} failed[/]",
            "",
            f"[{_GOLD}]{escape(str(d.get('headline', 'The run failed.')))}[/]",
            "",
            f"[bold]Next:[/] {escape(str(d.get('next_step', '')))}",
        ]
        if d.get("crash_log"):
            head.append(f"[{_DIM}]crash log: {escape(str(d['crash_log']))}[/]")
        with Vertical(id="dialog"):
            yield Static("\n".join(head), id="dtext")
            with VerticalScroll(id="failtail"):
                yield Static(f"[{_DIM}]{escape(str(d.get('tail') or 'no log output'))}[/]", id="failtailtext")
            yield Button("Close", id="close")
        yield Footer()

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()
