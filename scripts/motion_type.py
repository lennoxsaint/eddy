#!/usr/bin/env python3
"""Premium minimal typographic motion overlay (ffmpeg drawtext).

Bold sparse type, ONE accent color, generous whitespace, a few words at a time — the goal-prompt's
motion aesthetic, done deterministically in ffmpeg (no headless browser, no panic risk). Each beat is
a keyword line (optionally a small kicker line above it) that fades in/out over a time window and sits
in a placement that must not cover the face PiP / picker / proof.

beats.json: [{"text","start","end","size","color","x","y","align":"l|c",
              "kicker"(optional),"kicker_size"(optional),"kicker_color"(optional)}]
x/y anchor the keyword; align l = x is left edge, c = x is center. Kicker sits above the keyword.

Usage: motion_type.py --in in.mp4 --out out.mp4 --beats beats.json --font font.ttf [--fontindex 0] [--fade 0.25]
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

CYAN = "0x4AA3FF"
WHITE = "0xF5FAFF"
DARK = "0x0B0B16"


def esc(t: str) -> str:
    # drawtext text escaping
    return (t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
            .replace("%", "\\%"))


def color(c: str) -> str:
    return {"cyan": CYAN, "white": WHITE, "dark": DARK}.get(c, c or WHITE)


def draw(text, start, end, size, col, x, y, align, fade, font, fontindex):
    xexpr = f"{x}" if align == "l" else f"({x})-(tw/2)"
    alpha = (f"if(between(t\\,{start}\\,{end})\\,"
             f"min(1\\,min((t-{start})/{fade}\\,({end}-t)/{fade}))\\,0)")
    return (
        f"drawtext=fontfile='{font}':text='{esc(text)}':"
        f"fontcolor={color(col)}:fontsize={size}:x={xexpr}:y={y}:"
        f"borderw=3:bordercolor={DARK}@0.85:shadowcolor=black@0.5:shadowx=2:shadowy=3:"
        f"alpha='{alpha}':enable='between(t,{start},{end})'"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--beats", required=True)
    ap.add_argument("--font", required=True)
    ap.add_argument("--fontindex", type=int, default=0)
    ap.add_argument("--fade", type=float, default=0.25)
    ap.add_argument("--audio", default="copy", help="copy | reencode")
    args = ap.parse_args()

    beats = json.load(open(args.beats))
    filters = []
    for b in beats:
        size = int(b.get("size", 64))
        x = b.get("x", 60); y = b.get("y", 900); align = b.get("align", "l")
        if b.get("kicker"):
            ksize = int(b.get("kicker_size", max(26, size // 2)))
            filters.append(draw(b["kicker"], b["start"], b["end"], ksize,
                                b.get("kicker_color", "white"), x, y - int(ksize * 1.35),
                                align, args.fade, args.font, args.fontindex))
        filters.append(draw(b["text"], b["start"], b["end"], size, b.get("color", "cyan"),
                            x, y, align, args.fade, args.font, args.fontindex))
    vf = ",".join(filters)

    acodec = ["-c:a", "copy"] if args.audio == "copy" else ["-c:a", "aac", "-b:a", "192k"]
    cmd = ["ffmpeg", "-y", "-i", args.inp, "-vf", vf,
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", *acodec,
           "-movflags", "+faststart", args.out]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2500:], file=sys.stderr)
        return 1
    print(json.dumps({"event": "motion", "beats": len(beats), "out": args.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
