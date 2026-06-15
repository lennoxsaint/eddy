"""Geometry invariants for the Shorts layout constants (1080x1920 standard).

These assert concrete numeric relationships between the panel/caption/face zones —
if someone restyles the layout and breaks the canvas math (panels off-canvas,
caption zone colliding with a panel, centering broken), one of these fails.
No rendering happens here; we only check the pure constants.
"""

from __future__ import annotations

from eddy.render import layout as L


def test_canvas_is_vertical_1080x1920():
    assert (L.W, L.H) == (1080, 1920)
    assert L.H > L.W  # portrait Shorts canvas


def test_face_panel_fits_horizontally_and_is_centered():
    # face square sits fully inside the canvas width
    assert L.FACE_X >= 0
    assert L.FACE_X + L.FACE_SIZE <= L.W
    # centered: left margin equals right margin
    right_margin = L.W - (L.FACE_X + L.FACE_SIZE)
    assert L.FACE_X == right_margin


def test_screen_panel_fits_and_is_centered():
    assert L.SCREEN_X >= 0
    assert L.SCREEN_X + L.SCREEN_W <= L.W
    right_margin = L.W - (L.SCREEN_X + L.SCREEN_W)
    assert L.SCREEN_X == right_margin


def test_degraded_panel_fits_and_is_centered():
    assert L.PANEL_X >= 0
    assert L.PANEL_X + L.PANEL_W <= L.W
    right_margin = L.W - (L.PANEL_X + L.PANEL_W)
    assert L.PANEL_X == right_margin


def test_face_above_caption_zone():
    # the face square ends at or before the caption zone begins
    assert L.FACE_Y + L.FACE_SIZE <= L.CAPTION_Y


def test_caption_zone_sits_between_face_and_screen():
    caption_bottom = L.CAPTION_Y + L.CAPTION_H
    # caption starts after the face ends...
    assert L.CAPTION_Y >= L.FACE_Y + L.FACE_SIZE
    # ...and ends before the screen panel starts (no overlap)
    assert caption_bottom <= L.SCREEN_Y


def test_all_vertical_zones_fit_within_canvas_height():
    assert L.FACE_Y >= 0
    assert L.FACE_Y + L.FACE_SIZE <= L.H
    assert L.CAPTION_Y + L.CAPTION_H <= L.H
    assert L.SCREEN_Y + L.SCREEN_H <= L.H


def test_corner_radius_does_not_exceed_smallest_panel_half():
    # a rounded corner radius larger than half a side would invert the geometry
    smallest_side = min(L.FACE_SIZE, L.SCREEN_W, L.SCREEN_H, L.PANEL_W)
    assert 0 < L.RADIUS <= smallest_side / 2


def test_cut_handles_ordered_and_within_gap_threshold():
    # boundary handles must be positive and never exceed the gap that triggers a cut
    handles = (L.START_HANDLE, L.INTERNAL_END_HANDLE, L.FINAL_END_HANDLE, L.MIN_BOUNDARY_HANDLE)
    for h in handles:
        assert 0 < h < L.GAP_CUT_THRESHOLD
    # the minimum boundary handle is the floor; the final-end handle is the most generous
    assert L.MIN_BOUNDARY_HANDLE <= L.START_HANDLE
    assert L.INTERNAL_END_HANDLE < L.FINAL_END_HANDLE
    assert L.GLUED_WORD_GAP < L.GAP_CUT_THRESHOLD


def test_caption_cue_budget_is_sane():
    # a cue can't be wider than the canvas and the small font is smaller than the big one
    assert L.CUE_MAX_PX <= L.W
    assert L.CAPTION_FONT_XS < L.CAPTION_FONT_S
    assert L.CUE_MAX_WORDS >= 1
    assert L.CUE_MAX_S > 0


def test_highlight_and_word_colors_are_valid_rgba():
    for rgba in (L.HIGHLIGHT_BLUE, L.WORD_SPOKEN, L.WORD_FUTURE, L.STROKE_DARK, L.STROKE_DIM):
        assert len(rgba) == 4
        for channel in rgba:
            assert 0 <= channel <= 255
    # spoken text is brighter (higher alpha) than not-yet-spoken text
    assert L.WORD_SPOKEN[3] > L.WORD_FUTURE[3]
