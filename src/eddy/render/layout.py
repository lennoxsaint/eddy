"""Shorts layout constants — the Yassy-approved stacked standard.

Camera square top, karaoke captions in the middle, screen/proof panel bottom. Do not restyle
without updating the source-lock/style-lock tests.
"""

from __future__ import annotations

W, H = 1080, 1920
BG = "0x0b0b0b"

# dual-source (camera + screen) stacked layout
# Yassy style-lock: camera reaches the top/side edges, one-line karaoke strip sits between,
# and the screen/proof panel reaches the side edges with only a tiny breathing gap.
FACE_SIZE = 1080
FACE_X = 0
FACE_Y = 0
CAPTION_Y = 1080
CAPTION_H = 150
SCREEN_W = 1080
SCREEN_H = 608
SCREEN_X = 0
SCREEN_Y = 1230
RADIUS = 30
FACE_RADIUS = 30
SCREEN_RADIUS = 28

# degraded single-composite layout (primary path for composite recordings):
# one large rounded panel above the caption zone, navy elsewhere.
PANEL_W = 1040
PANEL_X = (W - PANEL_W) // 2

# cut-safety handles (seconds) — hard rules from the approved standard
GAP_CUT_THRESHOLD = 0.68
START_HANDLE = 0.24
INTERNAL_END_HANDLE = 0.32
FINAL_END_HANDLE = 0.52
GLUED_WORD_GAP = 0.08
MIN_BOUNDARY_HANDLE = 0.10

# karaoke captions
CAPTION_FONT_S = 58
CAPTION_FONT_XS = 50
CUE_MAX_WORDS = 5
CUE_MAX_S = 2.0
CUE_MAX_PX = 1010
HIGHLIGHT_BLUE = (74, 163, 255, 235)
WORD_SPOKEN = (245, 250, 255, 255)
WORD_FUTURE = (132, 145, 160, 125)
STROKE_DARK = (1, 10, 22, 230)
STROKE_DIM = (1, 10, 22, 120)
