"""`EddyApp` — the full-screen Textual application bare `eddy` launches.

Thin shell: it owns the data layer (`TuiData`, which wraps the shared JobManager) and pushes the home
screen. `run_tui()` is what the CLI calls on an interactive terminal.
"""

from __future__ import annotations

from textual.app import App

from eddy.tui.runner import TuiData


class EddyApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "EDDY"
    BINDINGS = [("ctrl+c", "quit", "Quit"), ("ctrl+q", "quit", "Quit")]

    def __init__(self, data: TuiData | None = None) -> None:
        super().__init__()
        self._data = data

    def on_mount(self) -> None:
        from eddy.tui.screens.home import HomeScreen

        self.push_screen(HomeScreen(self._data or TuiData()))


def run_tui(data: TuiData | None = None) -> None:
    """Launch the Eddy TUI (blocks until the user quits)."""
    EddyApp(data=data).run()
