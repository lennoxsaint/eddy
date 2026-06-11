"""Shorts layout constants — the approved "Clients Hunt You v3" standard
(docs/references/shorts-rendering-standard.md). Do not restyle without approval."""

from __future__ import annotations

W, H = 1080, 1920
BG = "0x07111f"  # deep navy

# dual-source (camera + screen) stacked layout
FACE_SIZE = 900
FACE_X = (W - FACE_SIZE) // 2
FACE_Y = 34
CAPTION_Y = 944
CAPTION_H = 250
SCREEN_W = 1000
SCREEN_H = 562
SCREEN_X = (W - SCREEN_W) // 2
SCREEN_Y = 1254
RADIUS = 34

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
CAPTION_FONT_S = 55
CAPTION_FONT_XS = 48
CUE_MAX_WORDS = 6
CUE_MAX_S = 2.0
CUE_MAX_PX = 930
HIGHLIGHT_BLUE = (20, 118, 205, 220)
WORD_SPOKEN = (245, 250, 255, 255)
WORD_FUTURE = (132, 145, 160, 125)
STROKE_DARK = (1, 10, 22, 230)
STROKE_DIM = (1, 10, 22, 120)
