"""Pixel-art rendering for Eddy's sprite.

Box-drawing glyphs can't actually look like an eagle, so the sprite is a real palette-indexed
*bitmap* and we render it two ways from one source of truth:

* `to_text()` — the terminal, using the upper-half-block trick (``▀`` with foreground = top pixel
  and background = bottom pixel). Each character cell shows two vertically-stacked pixels, so a
  bitmap renders at full image fidelity and roughly square aspect — the same approach `chafa`/`timg`
  use to show images in a terminal.
* `to_png()` — a scaled PNG (via the bundled `pillow`), used to *visually verify* the art looks like
  an eagle and as an export for docs.

A bitmap is a list of equal-length strings; each character is a palette key. ``.`` is transparent.
"""

from __future__ import annotations

from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from rich.text import Text

# Bald-eagle palette. Keys are single chars used in the bitmaps; values are RGB (None = transparent).
PALETTE: dict[str, tuple[int, int, int] | None] = {
    ".": None,             # transparent
    "W": (242, 244, 248),  # white head / tail feathers
    "w": (203, 209, 220),  # white feather shadow
    "D": (62, 45, 32),     # dark brown body
    "B": (104, 76, 48),    # mid brown wing
    "b": (140, 104, 64),   # light brown feather highlight
    "G": (245, 184, 42),   # gold beak / talons
    "g": (201, 142, 24),   # gold shadow
    "K": (24, 19, 16),     # outline / pupil
    "Y": (252, 216, 96),   # eye iris / highlight
    "r": (170, 70, 40),    # warm shadow under beak
}


def _rgb(key: str) -> tuple[int, int, int] | None:
    return PALETTE.get(key)


def _hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def width(bitmap: list[str]) -> int:
    return max((len(r) for r in bitmap), default=0)


def to_text(bitmap: list[str]) -> Text:
    """Render a bitmap to a Rich `Text` using half-block characters (2 pixels per character cell)."""
    w = width(bitmap)
    rows = [r.ljust(w, ".") for r in bitmap]
    if len(rows) % 2:  # need an even number of pixel rows to pair them
        rows.append("." * w)
    text = Text()
    for top_row, bot_row in zip(rows[0::2], rows[1::2]):
        for top_key, bot_key in zip(top_row, bot_row):
            top, bot = _rgb(top_key), _rgb(bot_key)
            if top is None and bot is None:
                text.append(" ")
            elif top is not None and bot is None:
                text.append("▀", Style(color=_hex(top)))
            elif top is None and bot is not None:
                text.append("▄", Style(color=_hex(bot)))
            elif top is not None and bot is not None:
                text.append("▀", Style(color=_hex(top), bgcolor=_hex(bot)))
        text.append("\n")
    text.rstrip()
    return text


def to_segments(bitmap: list[str]) -> list[Segment]:
    """Half-block render as raw Rich Segments (handy for measuring / embedding)."""
    return list(to_text(bitmap).render(None))  # type: ignore[arg-type]


def to_png(bitmap: list[str], path: str | Path, scale: int = 16, bg: tuple[int, int, int] = (140, 140, 146)) -> Path:
    """Write a scaled PNG of the bitmap (transparent pixels filled with `bg` so shape is visible)."""
    from PIL import Image, ImageDraw

    w = width(bitmap)
    h = len(bitmap)
    img = Image.new("RGB", (w * scale, h * scale), bg)
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(bitmap):
        for x, key in enumerate(row.ljust(w, ".")):
            rgb = _rgb(key)
            if rgb is None:
                continue
            draw.rectangle([x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1], fill=rgb)
    out = Path(path)
    img.save(out)
    return out
