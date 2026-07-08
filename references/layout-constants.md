# Frozen layout constants — never re-derive

These are V1's proven, Yassy-approved numbers (`~/eddy/src/eddy/render/layout.py`). The model must
NOT recompute geometry per run — `scripts/composite_render.py` reads these. They are the look Lennox
already approved.

## YouTube long — 1920×1080

- Screen recording is the **base layer** (padded/fit to 1920×1080, black bars if needed, `setsar=1`).
- Webcam **PiP** bottom-right: **260×260**, corner **radius 30**, **margin 0** from the edges.
  - At 1080p: `cam_x = 1920 - 260 - 0 = 1660`, `cam_y = 1080 - 260 - 0 = 820`.
  - Rounded corners = PIL rounded-rectangle **alpha mask** → `alphamerge` → `overlay` (V1 method):
    `[cam_scaled][mask]alphamerge[cam]; [screen][cam]overlay=1660:820:format=auto`.
  - Scale all three values by `out_h/1080` for other output heights.
- Talking-head fallback (camera only, no screen): fill the 16:9 frame with the head; captions in the
  lower third.

## Shorts — 1080×1920 (dual-source stacked)

- Canvas `W,H = 1080,1920`, background `0x0b0b0b`.
- **Face** square: `1080×1080` at `(0, 0)`, radius **30**.
- **Caption** strip: `y=1080`, height **150**.
- **Screen/proof** panel: `1080×608` at `(0, 1230)`, radius **28**.
- Talking-head-only Short: fill 9:16 with the head, captions at `y=1320`.

## Karaoke captions (style reference)

Rendered by `embedded-captions` `anchor` (clean, non-chaotic). Match this style:

- ≤5 words per cue, ≤2.0s per cue, 2 lines max, UPPERCASE.
- Current word: white text on a **cyan rounded highlight** `RGBA(74,163,255,235)`.
- Already-spoken words: bright white `RGBA(245,250,255,255)`.
- Future words: dimmed `RGBA(132,145,160,125)`.
- Dark navy stroke `RGBA(1,10,22,230)`; +120ms tail after the last word.
- Font ~58px (50px fallback when a cue wraps).
- **One cue at a time — never a chaotic per-word storm.** (Tariq's explicit critique.)

## Cut-safety handles (seconds) — from the approved standard

- `START_HANDLE = 0.24` (pre-roll on first kept range)
- `INTERNAL_END_HANDLE = 0.32` (post-word handle on internal cuts)
- `FINAL_END_HANDLE = 0.52` (post-word handle on the final cut)
- `MIN_BOUNDARY_HANDLE = 0.10`
- `GAP_CUT_THRESHOLD = 0.68` (a gap ≥ this triggers a cut)
- `GLUED_WORD_GAP = 0.08` (min gap between words without cutting)

## Gap band (pacing gates)

- Median gap target **0.12-0.20s**, P95 **≤0.22s**, hard max **0.28s** for unprotected gaps.
- Word-gap tightening (SOP step 4): only gaps **>0.2s → 0.1s**; sacred pauses exempt.

## Studio Sound

Real Descript, audio-only. **Never** the V1 ffmpeg approximation.
