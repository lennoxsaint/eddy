"""The 'How do you want this edited?' chooser for multiple runnable edit paths."""

from __future__ import annotations

from typing import ClassVar, cast

from rich.markup import escape
from textual import events, on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static

_KEYS = ("1", "2", "3", "4", "5")


class EditPathScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = cast(
        list[Binding | tuple[str, str] | tuple[str, str, str]],
        [(key, f"pick_index({idx})", f"Option {idx + 1}") for idx, key in enumerate(_KEYS)]
        + [("escape", "cancel", "Cancel")],
    )

    def __init__(self, summary: str, plan: dict) -> None:
        super().__init__()
        self._summary = summary
        self._options = [option for option in plan.get("options", []) if option.get("runnable")]
        self._recommended = plan.get("recommended_option_id")

    def compose(self):
        lines = ["[#f5b836 bold]How do you want this edited?[/]", "", escape(self._summary), ""]
        for idx, option in enumerate(self._options[: len(_KEYS)], start=1):
            rec = " [#f5b836](recommended)[/]" if option.get("id") == self._recommended else ""
            benefits = "; ".join(option.get("benefits") or [])
            drawbacks = "; ".join(option.get("drawbacks") or [])
            lines.append(f"[bold]{idx}. {escape(option.get('label', option.get('id', 'Option')))}[/]{rec}")
            lines.append(escape(option.get("summary", "")))
            if benefits:
                lines.append(f"[#8b93a1]Good:[/] {escape(benefits)}")
            if drawbacks:
                lines.append(f"[#8b93a1]Tradeoff:[/] {escape(drawbacks)}")
            lines.append("")
        with Vertical(id="dialog"):
            yield Static("\n".join(lines).rstrip(), id="dtext")
            with Horizontal(id="dbtns"):
                for idx, option in enumerate(self._options[: len(_KEYS)], start=1):
                    label = f"{idx}. {option.get('label', option.get('id', 'Option'))}"
                    yield Button(label, variant="primary" if option.get("id") == self._recommended else "default", id=f"path-{idx}")
        yield Footer()

    def on_click(self, event: events.Click) -> None:
        if event.widget is self:
            self.dismiss(None)

    def action_pick_index(self, idx: int) -> None:
        if 0 <= idx < len(self._options):
            self.dismiss(str(self._options[idx]["id"]))

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("path-"):
            idx = int(event.button.id.split("-", 1)[1]) - 1
            self.action_pick_index(idx)
