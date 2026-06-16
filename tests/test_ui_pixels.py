"""The half-block pixel renderer: the bitmap -> terminal and bitmap -> PNG paths that make Eddy
actually look like an eagle. Pure logic + a tmp PNG; no terminal required."""

from __future__ import annotations

from eddy.ui import pixels


def test_width_handles_ragged_rows():
    assert pixels.width(["WW", "WWWW", "W"]) == 4
    assert pixels.width([]) == 0


def test_to_text_pairs_rows_into_half_blocks():
    # 4 pixel rows -> 2 character rows (two pixels per cell)
    bmp = ["WW", "WW", "DD", "DD"]
    text = pixels.to_text(bmp)
    assert text.plain.count("\n") == 1  # two rendered rows
    assert "▀" in text.plain


def test_to_text_transparency_uses_space_and_half_glyphs():
    # top transparent / bottom solid -> lower half block; both transparent -> space
    text = pixels.to_text([".W", "..", "W.", ".."])
    assert "▄" in text.plain or "▀" in text.plain
    assert " " in text.plain


def test_to_text_odd_rows_padded():
    # an odd number of pixel rows must not drop the last row
    text = pixels.to_text(["WW", "WW", "DD"])
    assert text.plain.count("\n") == 1


def test_to_png_writes_file(tmp_path):
    out = pixels.to_png(["WG", "DK"], tmp_path / "x.png", scale=4)
    assert out.exists() and out.stat().st_size > 0


def test_palette_has_transparent_and_eagle_colours():
    assert pixels.PALETTE["."] is None
    for key in ("W", "D", "G", "K", "Y"):  # white head, brown body, gold beak, outline, eye
        assert isinstance(pixels.PALETTE[key], tuple)
