from __future__ import annotations

from textual.app import App
from textual.widgets import Button

from eddy.tui.screens.edit_path import EditPathScreen


class _Host(App):
    def __init__(self) -> None:
        super().__init__()
        self.result: object = "unset"

    def on_mount(self) -> None:
        self.push_screen(
            EditPathScreen(
                "run ~/x.mp4",
                {
                    "recommended_option_id": "host_kernel",
                    "options": [
                        {
                            "id": "host_kernel",
                            "label": "Use this assistant",
                            "runnable": True,
                            "summary": "Best current assistant path.",
                            "benefits": ["Usually best quality"],
                            "drawbacks": ["Transcript goes to the assistant"],
                        },
                        {
                            "id": "local_high_quality",
                            "label": "Use local model",
                            "runnable": True,
                            "summary": "Most private path.",
                            "benefits": ["Private"],
                            "drawbacks": ["Slower"],
                        },
                    ],
                },
            ),
            self._got,
        )

    def _got(self, value: str | None) -> None:
        self.result = value


async def test_edit_path_screen_shows_plain_english_choices():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        text = app.screen.query_one("#dtext").render()
        assert "How do you want this edited?" in str(text)
        assert "Good:" in str(text)
        assert "Tradeoff:" in str(text)
        ids = {button.id for button in app.screen.query(Button)}
        assert ids == {"path-1", "path-2"}


async def test_edit_path_key_returns_option_id():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()
    assert app.result == "local_high_quality"
