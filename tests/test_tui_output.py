"""The 'What should Eddy make?' chooser (OutputScreen): three choice buttons (no clipped Cancel),
the choice -> skip-flags mapping, and the two cancel paths (esc + click on the backdrop)."""

from __future__ import annotations

from textual.app import App
from textual.widgets import Button

from eddy.tui.screens.output import OUTPUT_FLAGS, OutputScreen


class _Host(App):
    """Mounts the chooser alone and captures whatever it dismisses with."""

    def __init__(self) -> None:
        super().__init__()
        self.result: object = "unset"

    def on_mount(self) -> None:
        self.push_screen(OutputScreen("run ~/x.mp4 [extract] only the Codex bit"), self._got)

    def _got(self, value: str | None) -> None:
        self.result = value


def test_output_flags_mapping_unchanged():
    # video = just the long (skip both); shorts = +clips, no package; kit = everything
    assert OUTPUT_FLAGS == {"video": (True, True), "shorts": (False, True), "kit": (False, False)}


async def test_chooser_has_three_choice_buttons_and_no_cancel():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        ids = {b.id for b in app.screen.query(Button)}
        assert ids == {"video", "shorts", "kit"}  # the clipped 4th 'cancel' button is gone


async def test_key_pick_returns_choice():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("k")
        await pilot.pause()
    assert app.result == "kit"


async def test_escape_cancels():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert app.result is None


async def test_click_on_backdrop_cancels():
    # the dialog is centred; (1, 1) is the dim backdrop -> a mouse cancel without a Cancel button
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click(offset=(1, 1))
        await pilot.pause()
    assert app.result is None
