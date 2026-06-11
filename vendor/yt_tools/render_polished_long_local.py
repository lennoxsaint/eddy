#!/usr/bin/env python3
"""Render a polished local long assembly from cleaned synced tracks."""

from __future__ import annotations

import shlex
import subprocess
import argparse
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path("/Users/yassybabes/YouTube")
FFMPEG = "/Users/yassybabes/.homebrew/bin/ffmpeg"
FFPROBE = "/Users/yassybabes/.homebrew/bin/ffprobe"
SCREEN = ROOT / "source/work/screen_long_cut_synced.mp4"
CAMERA = ROOT / "source/work/camera_long_cut.mp4"
OUT_DIR = ROOT / "source/exports"
ASSET_DIR = ROOT / "source/work/polished_long_assets"
OUT = OUT_DIR / "Codex-2026-05-29-landed-2300-month-client-long-sop-polished-local.mp4"


def make_mask(path: Path, size: tuple[int, int], radius: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    mask.save(path)


def media_duration(path: Path) -> float:
    output = subprocess.check_output(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    )
    return float(output.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=Path, default=SCREEN)
    parser.add_argument("--camera", type=Path, default=CAMERA)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    duration = media_duration(args.camera)
    screen_mask = ASSET_DIR / "screen-mask-1840x1035-r100.png"
    camera_mask = ASSET_DIR / "camera-mask-240x240-r100.png"
    make_mask(screen_mask, (1840, 1035), 100)
    make_mask(camera_mask, (240, 240), 100)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    filter_complex = ";".join(
        [
            f"color=c=0x07111f:s=1920x1080:r=30:d={duration:.3f}[bg]",
            "[0:v]scale=1840:1035,setpts=PTS-STARTPTS,format=rgba[screen_rgba]",
            "[2:v]format=gray[screen_mask]",
            "[screen_rgba][screen_mask]alphamerge[screen_round]",
            "[bg][screen_round]overlay=40:22[screen_base]",
            "[1:v]crop=1080:1080:420:0,scale=240:240,setpts=PTS-STARTPTS,format=rgba[cam_rgba]",
            "[3:v]format=gray[cam_mask]",
            "[cam_rgba][cam_mask]alphamerge[cam_round]",
            "[screen_base][cam_round]overlay=1632:792[v]",
            "[1:a]aresample=async=1:first_pts=0,afftdn=nf=-25,acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120,dynaudnorm=f=75:g=9,alimiter=limit=0.95,aresample=48000[a]",
        ]
    )

    cmd = [
        FFMPEG,
        "-y",
        "-hide_banner",
            "-i",
            str(args.screen),
            "-i",
            str(args.camera),
        "-loop",
        "1",
        "-i",
        str(screen_mask),
        "-loop",
        "1",
        "-i",
        str(camera_mask),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "h264_videotoolbox",
        "-allow_sw",
        "1",
        "-b:v",
        "10000k",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(args.out),
    ]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
