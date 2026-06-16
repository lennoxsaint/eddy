"""A modal that tabs through a finished run's launch-kit artifacts — titles, description, chapters,
REVIEW.md, captions — as text, plus a stub for the binary deliverables (video / thumbnails). The
whole point of Eddy is to hand back a kit the creator trusts; this lets them read it without leaving
the app for a file manager."""

from __future__ import annotations

from rich.markup import escape
from textual import on
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static

_GOLD = "#f5b836"
_DIM = "#8b909b"


def _human(size: int) -> str:
    f = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{size} B"


class PreviewScreen(ModalScreen[None]):
    BINDINGS = [
        ("escape", "close", "Close"),
        ("right", "next", "Next"),
        ("left", "prev", "Prev"),
        ("down", "next", "Next"),
        ("up", "prev", "Prev"),
        ("o", "reveal", "Open folder"),
    ]

    def __init__(self, data, slug: str) -> None:
        super().__init__()
        self._data = data
        self._slug = slug
        self._items = data.artifacts(slug)
        self._i = 0

    def compose(self):
        with Vertical(id="dialog"):
            yield Static(id="ptitle")
            with VerticalScroll(id="pbody"):
                yield Static(id="pbodytext")
            yield Button("Close", id="close")
        yield Footer()

    def on_mount(self) -> None:
        self._render_item()

    def _render_item(self) -> None:
        title = self.query_one("#ptitle", Static)
        body = self.query_one("#pbodytext", Static)
        if not self._items:
            title.update(f"[{_GOLD} bold]{escape(self._slug)}[/]  [{_DIM}]no results yet[/]")
            body.update(f"[{_DIM}]This run hasn't produced a final/ kit. Edit or render it first.[/]")
            return
        it = self._items[self._i]
        title.update(
            f"[{_GOLD} bold]{escape(self._slug)}[/]  [{_DIM}][{self._i + 1}/{len(self._items)}] "
            f"{escape(it['name'])}  ·  ←/→ to browse · o opens the folder[/]"
        )
        if it["kind"] == "text":
            text = self._data.artifact_text(self._slug, it["name"]) or ""
            body.update(escape(text) if text.strip() else f"[{_DIM}](empty file)[/]")
        elif it["kind"] == "folder":
            body.update(f"[{_DIM}]folder · {it['size']} item(s) — press o to open it in your file manager[/]")
        else:
            body.update(f"[{_DIM}]{it['kind']} file · {_human(it['size'])} — press o to open the results folder[/]")

    def action_next(self) -> None:
        if self._items:
            self._i = (self._i + 1) % len(self._items)
            self._render_item()

    def action_prev(self) -> None:
        if self._items:
            self._i = (self._i - 1) % len(self._items)
            self._render_item()

    def action_reveal(self) -> None:
        self._data.reveal(self._slug)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()
