# Two-layer ingest (camera + screen) for proper Shorts

Eddy renders Shorts in Yasmine's approved stacked layout — **talking-head on top, screen
recording uncropped on the bottom, karaoke captions in the gap between them** (navy background,
1080×1920). This layout only works when Eddy is given the two layers *separately*. If it only
receives a single composite (camera PIP burned into the screen recording), it falls back to a
degraded single-panel layout.

## How to record + export (Descript)

Film with two tracks: your **camera** (talking head) and the **screen** recording. Export them as
**separate files**, not a flattened composite. Yasmine's bridge for this is
`yassy-mbp:~/YouTube/tools/descript_multitrack_delivery.py` (camera + screen tracks at offset 0).

## How to hand them to Eddy

Put the files in a folder and point `eddy run` at the folder:

```
my-video/
  camera.mp4    # talking head, 1920×1080  (also matched: *cam*, *webcam*, *face*, *talking*)
  screen.mp4    # screen recording          (also matched: *display*)
  mic.wav       # optional external mic (else camera audio is used)
```

```bash
eddy run path/to/my-video/
```

`discover_sources()` matches by filename, records each with a SHA-256, and the renderer takes the
dual path automatically when a `screen` file is present. A single file (or a folder with one video)
still works — it just uses the degraded single-composite layout.

## Geometry (Yasmine's standard, do not restyle without approval)

- Face: 900×900 square, centered, top (Y=34), 34px rounded corners — camera center-cropped to square.
- Captions: 1080×250 band at Y=944 (the gap above the screen), blue current-word highlight.
- Screen: 1000×562 at Y=1254, `force_original_aspect_ratio=decrease` + pad — **uncropped**,
  letterboxed/centered, leaving a safe gap at the very bottom.
