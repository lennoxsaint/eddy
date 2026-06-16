"""Eddy the eagle as data: state frames, sizes, the inline mark, and the no-colour ASCII fallback."""

from __future__ import annotations

from eddy.ui import sprite


def test_all_states_have_frames_at_both_sizes():
    for state in sprite.STATES:
        for small in (False, True):
            loop = sprite.frames(state, small=small)
            assert loop and all(isinstance(f, list) for f in loop)


def test_unknown_state_falls_back_to_idle():
    assert sprite.frames("nonsense") == sprite.frames("idle")


def test_frame_index_wraps():
    loop = sprite.frames("idle")
    assert sprite.frame("idle", index=len(loop)) == loop[0]
    assert sprite.frame("idle", index=len(loop) + 1) == loop[1 % len(loop)]


def test_hero_and_small_differ_in_size():
    assert max(map(len, sprite.HERO)) > max(map(len, sprite.SMALL))


def test_states_are_distinct_edits_not_identical():
    # working (focused, no glint) must differ from idle (yellow glint) — proves the patch applied
    assert sprite.frame("working", small=True) != sprite.frame("idle", small=True)
    assert sprite.frame("success", small=True) != sprite.frame("idle", small=True)


def test_chibi_eaglet_palette_keys_present_in_art():
    flat = "".join("".join(row) for row in sprite.HERO)
    for key in ("W", "D", "G", "K", "H", "p"):  # white head, brown body, gold beak, pupil, sparkle, blush
        assert key in flat


def test_ascii_fallback_and_mini_exist():
    assert sprite.ascii_art().strip()
    assert "eddy.eye" in sprite.MINI  # themed inline mark
