#!/usr/bin/env python3
"""Render first-pass vertical shorts from marked raw-source ranges."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


ROOT = Path(os.environ.get("EDDY_YT_TOOLS_ROOT", "~/YouTube")).expanduser()
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
CAMERA = ROOT / "source/raw/camera.mp4"
SCREEN = ROOT / "source/raw/screen.mp4"
OUT_DIR = ROOT / "source/exports/shorts"

SHORTS = [
    {
        "title": "Proof Beats Subscribers",
        "segments": [(959.35, 1033.17)],
        "headline": "PROOF BEATS SUBSCRIBERS",
    },
    {
        "title": "Clients Hunt You",
        "segments": [(1329.40, 1421.01)],
        "headline": "CLIENTS CAN FIND YOU FIRST",
    },
    {
        "title": "Show Systems Not Pitches",
        "segments": [(1646.97, 1737.20)],
        "headline": "SHOW THE SYSTEM",
    },
    {
        "title": "Your Weird Skill Stack",
        "segments": [(2119.92, 2209.06)],
        "headline": "STACK YOUR WEIRD SKILLS",
    },
    {
        "title": "Do Free Work Strategically",
        "segments": [(2653.72, 2711.88), (2793.28, 2818.07)],
        "headline": "FREE WORK, ON PURPOSE",
    },
    {
        "title": "Let Them Name Price",
        "segments": [(3149.28, 3154.02), (3230.95, 3250.85), (3259.69, 3304.47)],
        "headline": "DO NOT PRICE FIRST",
    },
    {
        "title": "Do Not Sign First Contract",
        "segments": [(3504.60, 3567.16), (3615.39, 3628.38)],
        "headline": "CHECK THE CONTRACT",
    },
    {
        "title": "Small Audience Real Client",
        "segments": [
            (280.893, 287.946),
            (299.760, 308.821),
            (313.656, 319.811),
            (323.922, 324.128),
            (324.879, 325.100),
            (327.040, 329.811),
            (330.831, 332.484),
            (334.502, 337.000),
        ],
        "headline": "SMALL AUDIENCE, REAL CLIENT",
    },
    {
        "title": "Proof In Twelve Seconds",
        "segments": [
            (661.741, 662.078),
            (664.678, 682.950),
            (683.295, 686.626),
            (687.262, 697.060),
            (724.990, 727.571),
            (728.814, 737.080),
        ],
        "headline": "PROOF IN 12 SECONDS",
    },
    {
        "title": "Ask The Win Question",
        "segments": [
            (1990.000, 1996.487),
            (2004.254, 2010.431),
            (2019.485, 2023.545),
            (2026.997, 2037.100),
            (2049.862, 2061.960),
        ],
        "headline": "ASK THE WIN QUESTION",
    },
    {
        "title": "One Skill Is Common",
        "segments": [
            (2288.000, 2291.084),
            (2291.678, 2298.289),
            (2299.226, 2302.122),
            (2308.118, 2310.784),
            (2311.694, 2318.657),
            (2319.532, 2330.903),
            (2331.731, 2336.578),
            (2351.450, 2351.653),
            (2379.011, 2384.093),
            (2385.094, 2389.207),
            (2390.256, 2391.000),
        ],
        "headline": "ONE SKILL IS COMMON",
    },
    {
        "title": "Bounded First Phase",
        "segments": [
            (3293.000, 3297.471),
            (3298.072, 3302.097),
            (3304.107, 3310.450),
            (3312.700, 3316.333),
            (3317.155, 3317.973),
            (3324.387, 3329.357),
            (3330.230, 3336.398),
            (3337.668, 3340.486),
            (3340.861, 3342.710),
        ],
        "headline": "BOUND THE FIRST PHASE",
    },
    {
        "title": "Random Mix Is Valuable",
        "segments": [
            (3912.880, 3916.616),
            (3918.637, 3920.314),
            (3922.563, 3926.763),
            (3946.681, 3949.766),
            (3951.410, 3955.773),
            (3958.531, 3967.352),
            (3968.782, 3970.540),
            (3970.909, 3982.000),
        ],
        "headline": "YOUR RANDOM MIX MATTERS",
    },
    {
        "title": "Make Proof This Week",
        "segments": [
            (3999.867, 4011.572),
            (4012.495, 4015.148),
            (4016.944, 4022.966),
            (4024.409, 4033.759),
            (4034.230, 4035.160),
        ],
        "headline": "MAKE PROOF THIS WEEK",
    },
    {
        "title": "Share Your Losses",
        "segments": [
            (4136.010, 4140.140),
            (4141.029, 4150.909),
            (4151.529, 4153.761),
            (4154.191, 4154.438),
            (4159.166, 4163.274),
            (4164.435, 4165.586),
            (4166.182, 4176.231),
            (4179.134, 4191.650),
        ],
        "headline": "SHARE YOUR LOSSES",
    },
]


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render(short: dict) -> None:
    title = short["title"]
    slug = title.lower().replace(" ", "-")
    out = OUT_DIR / f"{slug}.mp4"
    segments = short["segments"]
    parts = []
    screen_labels = []
    camera_labels = []
    audio_labels = []
    for idx, (start, end) in enumerate(segments):
        parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,"
            f"scale=1080:760:force_original_aspect_ratio=increase,"
            f"crop=1080:760,setsar=1[sv{idx}]"
        )
        parts.append(
            f"[1:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,"
            f"crop=1080:1080:420:0,scale=820:820,setsar=1[cv{idx}]"
        )
        parts.append(
            f"[1:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{idx}]"
        )
        screen_labels.append(f"[sv{idx}]")
        camera_labels.append(f"[cv{idx}]")
        audio_labels.append(f"[a{idx}]")
    parts.append("".join(screen_labels) + f"concat=n={len(segments)}:v=1:a=0[s]")
    parts.append("".join(camera_labels) + f"concat=n={len(segments)}:v=1:a=0[c]")
    parts.append("".join(audio_labels) + f"concat=n={len(segments)}:v=0:a=1[a]")
    parts.append("[s]pad=1080:1920:0:110:color=0x07111f[bg]")
    parts.append("[bg][c]overlay=(W-w)/2:900[v]")
    filter_script = OUT_DIR / f"{slug}.filter.txt"
    filter_script.write_text(";\n".join(parts), encoding="utf-8")
    cmd = [
        FFMPEG,
        "-y",
        "-hide_banner",
        "-i",
        str(SCREEN),
        "-i",
        str(CAMERA),
        "-filter_complex_script",
        str(filter_script),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "h264_videotoolbox",
        "-allow_sw",
        "1",
        "-b:v",
        "7000k",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(out),
    ]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for short in SHORTS:
        render(short)


if __name__ == "__main__":
    main()
