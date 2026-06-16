"""A modal that runs Eddy's environment doctor (hardware + providers + preflight) in a worker thread
so the UI never blocks on the local-Ollama probe."""

from __future__ import annotations

import contextlib
import io

from textual import on, work
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class DoctorScreen(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Close")]

    def compose(self):
        with Vertical(id="dialog"):
            yield Static("[#f5b836 bold]doctor[/]\n\nchecking environment…", id="dtext")
            yield Button("Close", id="close")

    def on_mount(self) -> None:
        self._probe()

    @work(thread=True)
    def _probe(self) -> None:
        from eddy.doctor import detect, preflight

        with contextlib.redirect_stdout(io.StringIO()):  # detect() may print; keep it out of the UI
            try:
                det = detect()
                checks = preflight()
            except Exception as e:  # never let the modal crash the app
                det, checks = {"error": str(e)}, []
        self.app.call_from_thread(self._display, det, checks)

    def _display(self, det: dict, checks: list) -> None:
        hw = det.get("hardware", {})
        lines = [
            f"machine   {hw.get('chip', '?')} · {hw.get('ram_gb', '?')}GB",
            f"ollama    {', '.join(det.get('ollama_models', [])) or 'not running / no models'}",
            "",
        ]
        for c in checks:
            mark = "ok  " if c.get("ok") else "FAIL"
            lines.append(f"{mark} {c.get('check', ''):12} {c.get('detail', '')}")
        if "error" in det:
            lines.append(f"error: {det['error']}")
        self.query_one("#dtext", Static).update("[#f5b836 bold]doctor[/]\n\n" + "\n".join(lines))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()
