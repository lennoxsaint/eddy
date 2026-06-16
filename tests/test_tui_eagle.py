"""The animated eaglet widget renders each mood to themed half-block pixels."""

from __future__ import annotations

from rich.text import Text

from eddy.tui.widgets.eagle import EagleWidget, needs_ascii


def test_needs_ascii_below_256_colors():
    assert needs_ascii(None) is True  # no colour
    assert needs_ascii("standard") is True  # 16-colour terminal — half-blocks unreadable
    assert needs_ascii("256") is False
    assert needs_ascii("truecolor") is False


def test_renders_a_text_for_each_state():
    w = EagleWidget(small=True)
    assert w.state == "idle"
    for state in ("idle", "thinking", "working", "success", "error"):
        w._state = state
        r = w.render()
        assert isinstance(r, Text) and r.plain.strip()


def test_frame_advance_changes_nothing_fatal():
    w = EagleWidget(small=True)
    w._frame = 1  # a later animation frame still renders
    assert isinstance(w.render(), Text)


def test_small_and_hero_differ():
    small = EagleWidget(small=True).render().plain
    hero = EagleWidget(small=False).render().plain
    assert hero.count("\n") >= small.count("\n")  # hero is taller
