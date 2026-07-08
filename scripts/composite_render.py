#!/usr/bin/env python3
"""Composite renderer — the frozen V1 look (deterministic pixel geometry).

Distilled from eddy v1 render/ (layout.py + segments.py). The model never hand-computes geometry;
it calls this. Rounded corners are done HERE (Descript's web app can't), via the V1 method:
a Pillow rounded-rectangle alpha mask -> ffmpeg alphamerge -> overlay.

Modes:
  long   : screen recording (rounded, full-frame fill) as base + webcam PiP (rounded) flush bottom-right. 16:9.
  short  : dual-source Shorts stack (face square top / gap for captions / screen panel bottom). 9:16.
  th     : talking-head fill (camera only), captions burned separately. 9:16 or 16:9.

Usage:
  composite_render.py long  --screen s.mp4 --camera c.mp4 --out out.mp4 [--proxy] [--bg 0x0b0b0b]
  composite_render.py short --face f.mp4 --screen s.mp4 --out out.mp4 [--proxy]
  composite_render.py short --face f.mp4 --out out.mp4 [--proxy]        # talking-head short
  composite_render.py th    --camera c.mp4 --out out.mp4 --w 1920 --h 1080 [--proxy]

Captions are NOT burned here — use embedded-captions `anchor` (see references/motion-layer.md).
Radii/insets are the validated-on-footage tuning point; defaults come from V1.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw  # Pillow — same dep V1 uses for masks/captions

# --- Frozen V1 constants (references/layout-constants.md) ---
LONG_W, LONG_H = 1920, 1080
CAM_SIZE = 260
CAM_RADIUS = 30
SCREEN_RADIUS_LONG = 26     # slight rounding on the full-frame screen (corners reveal bg)
SCREEN_INSET = 0           # screen FILLS the frame — no border (was 24; caused a black margin)
CAM_EDGE_GAP = 0           # PiP flush to the bottom-right corner (was 32; caused a gap)

# Shorts (1080x1920)
S_W, S_H = 1080, 1920
FACE_SIZE = 1080
FACE_RADIUS = 30
CAPTION_Y, CAPTION_H = 1080, 150
SCREEN_PANEL_Y, SCREEN_PANEL_H = 1230, 608
SCREEN_RADIUS_SHORT = 28
BG_DEFAULT = "0x0b0b0b"


def rounded_mask(path: Path, w: int, h: int, radius: int) -> Path:
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def x264(proxy: bool) -> list[str]:
    return (["-c:v", "libx264", "-preset", "veryfast", "-crf", "26"] if proxy
            else ["-c:v", "libx264", "-preset", "medium", "-crf", "18"])


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2500:], file=sys.stderr)
        raise RuntimeError("ffmpeg composite failed")


def probe_dur(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def bound(*inputs: Path) -> list[str]:
    """`-t <min real-input duration>` — hard-bounds the output so infinite `-loop 1` mask
    inputs can never make the encode run forever (‑shortest alone fails when there's no audio)."""
    durs = [d for d in (probe_dur(p) for p in inputs) if d > 0]
    return ["-t", f"{min(durs):.3f}"] if durs else []


def scale_factor(proxy: bool) -> float:
    return 0.5 if proxy else 1.0


def render_long(screen: Path, camera: Path, out: Path, bg: str, proxy: bool, work: Path) -> None:
    f = scale_factor(proxy)
    W, H = int(LONG_W * f), int(LONG_H * f)
    inset = int(SCREEN_INSET * f)
    cam = int(CAM_SIZE * f)
    cam_r = max(8, int(CAM_RADIUS * f))
    scr_r = max(8, int(SCREEN_RADIUS_LONG * f))
    edge = int(CAM_EDGE_GAP * f)
    sw, sh = W - 2 * inset, H - 2 * inset
    cam_x, cam_y = W - cam - edge, H - cam - edge

    scr_mask = rounded_mask(work / f"scr-mask-{sw}x{sh}-r{scr_r}.png", sw, sh, scr_r)
    cam_mask = rounded_mask(work / f"cam-mask-{cam}-r{cam_r}.png", cam, cam, cam_r)

    fc = (
        f"color=c={bg}:s={W}x{H},format=rgba[bg];"
        f"[0:v]scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
        f"setsar=1,fps=30,format=rgba[scr0];"
        f"[2:v]format=gray,scale={sw}:{sh}[scrm];[scr0][scrm]alphamerge[scr];"
        f"[bg][scr]overlay={inset}:{inset}:shortest=1:format=auto[base];"
        f"[1:v]scale={cam}:{cam}:force_original_aspect_ratio=increase,crop={cam}:{cam},"
        f"setsar=1,fps=30,format=rgba[cam0];"
        f"[3:v]format=gray,scale={cam}:{cam}[camm];[cam0][camm]alphamerge[cam];"
        f"[base][cam]overlay={cam_x}:{cam_y}:format=auto,format=yuv420p[v]"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y",
        "-i", str(screen), "-i", str(camera),
        "-loop", "1", "-framerate", "30", "-i", str(scr_mask),
        "-loop", "1", "-framerate", "30", "-i", str(cam_mask),
        # audio = CAMERA (input 1) — the mic / Studio-Sound master, not the screen capture's audio.
        "-filter_complex", fc, "-map", "[v]", "-map", "1:a?",
        *x264(proxy), "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-r", "30", *bound(screen, camera), "-movflags", "+faststart", str(out),
    ])


def render_short_dual(face: Path, screen: Path, out: Path, bg: str, proxy: bool, work: Path) -> None:
    f = scale_factor(proxy)
    W, H = int(S_W * f), int(S_H * f)
    face_sz = int(FACE_SIZE * f)
    face_r = max(8, int(FACE_RADIUS * f))
    sp_y, sp_h = int(SCREEN_PANEL_Y * f), int(SCREEN_PANEL_H * f)
    scr_r = max(8, int(SCREEN_RADIUS_SHORT * f))

    face_mask = rounded_mask(work / f"face-mask-{face_sz}-r{face_r}.png", face_sz, face_sz, face_r)
    scr_mask = rounded_mask(work / f"sscr-mask-{W}x{sp_h}-r{scr_r}.png", W, sp_h, scr_r)

    fc = (
        f"color=c={bg}:s={W}x{H},format=rgba[bg];"
        f"[0:v]scale={face_sz}:{face_sz}:force_original_aspect_ratio=increase,crop={face_sz}:{face_sz},"
        f"setsar=1,fps=30,format=rgba[f0];"
        f"[2:v]format=gray,scale={face_sz}:{face_sz}[fm];[f0][fm]alphamerge[face];"
        f"[bg][face]overlay=0:0:shortest=1:format=auto[b1];"
        f"[1:v]scale={W}:{sp_h}:force_original_aspect_ratio=increase,crop={W}:{sp_h},"
        f"setsar=1,fps=30,format=rgba[s0];"
        f"[3:v]format=gray,scale={W}:{sp_h}[sm];[s0][sm]alphamerge[scr];"
        f"[b1][scr]overlay=0:{sp_y}:format=auto,format=yuv420p[v]"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y",
        "-i", str(face), "-i", str(screen),
        "-loop", "1", "-framerate", "30", "-i", str(face_mask),
        "-loop", "1", "-framerate", "30", "-i", str(scr_mask),
        "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
        *x264(proxy), "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-r", "30", *bound(face, screen), "-movflags", "+faststart", str(out),
    ])


def render_short_th(face: Path, out: Path, proxy: bool) -> None:
    f = scale_factor(proxy)
    W, H = int(S_W * f), int(S_H * f)
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"setsar=1,fps=30,format=yuv420p[v]")
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(face), "-filter_complex", fc,
         "-map", "[v]", "-map", "0:a?", *x264(proxy), "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(out)])


def render_th(camera: Path, out: Path, w: int, h: int, proxy: bool) -> None:
    f = scale_factor(proxy)
    W, H = int(w * f), int(h * f)
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"setsar=1,fps=30,format=yuv420p[v]")
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(camera), "-filter_complex", fc,
         "-map", "[v]", "-map", "0:a?", *x264(proxy), "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(out)])


def main() -> int:
    ap = argparse.ArgumentParser(description="Composite renderer (frozen V1 layout).")
    ap.add_argument("mode", choices=["long", "short", "th"])
    ap.add_argument("--screen")
    ap.add_argument("--camera")
    ap.add_argument("--face")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bg", default=BG_DEFAULT)
    ap.add_argument("--proxy", action="store_true")
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    args = ap.parse_args()

    out = Path(args.out)
    work = out.parent / "masks"
    work.mkdir(parents=True, exist_ok=True)

    try:
        if args.mode == "long":
            if not (args.screen and args.camera):
                print("ERROR: long mode needs --screen and --camera.", file=sys.stderr)
                return 2
            render_long(Path(args.screen), Path(args.camera), out, args.bg, args.proxy, work)
        elif args.mode == "short":
            if args.face and args.screen:
                render_short_dual(Path(args.face), Path(args.screen), out, args.bg, args.proxy, work)
            elif args.face:
                render_short_th(Path(args.face), out, args.proxy)
            else:
                print("ERROR: short mode needs --face (and optionally --screen).", file=sys.stderr)
                return 2
        else:  # th
            if not args.camera:
                print("ERROR: th mode needs --camera.", file=sys.stderr)
                return 2
            render_th(Path(args.camera), out, args.w, args.h, args.proxy)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4

    print(f'{{"event":"composited","mode":"{args.mode}","proxy":{str(args.proxy).lower()},'
          f'"out":"{out}"}}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
