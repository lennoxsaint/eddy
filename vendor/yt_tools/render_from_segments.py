#!/usr/bin/env python3
"""Render camera and screen cuts from a shared segment list."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path("/Users/yassybabes/YouTube")
FFMPEG = "/Users/yassybabes/.homebrew/bin/ffmpeg"


def load_segments(path: Path) -> list[dict[str, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["segments"]


def write_camera_filter(segments: list[dict[str, float]], path: Path) -> None:
    lines = []
    concat_inputs = []
    for idx, segment in enumerate(segments):
        start = segment["start"]
        end = segment["end"]
        lines.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{idx}];"
        )
        lines.append(
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{idx}];"
        )
        concat_inputs.append(f"[v{idx}][a{idx}]")
    lines.append("".join(concat_inputs) + f"concat=n={len(segments)}:v=1:a=1[outv][outa]")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_screen_filter(segments: list[dict[str, float]], path: Path) -> None:
    lines = []
    concat_inputs = []
    for idx, segment in enumerate(segments):
        start = segment["start"]
        end = segment["end"]
        lines.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{idx}];"
        )
        concat_inputs.append(f"[v{idx}]")
    lines.append("".join(concat_inputs) + f"concat=n={len(segments)}:v=1:a=0[outv]")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(cmd: list[str]) -> None:
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments", type=Path, default=ROOT / "source/edit/keep_segments.long.json")
    parser.add_argument("--camera-in", type=Path, default=ROOT / "source/raw/camera.mp4")
    parser.add_argument("--screen-in", type=Path, default=ROOT / "source/raw/screen.mp4")
    parser.add_argument("--camera-out", type=Path, default=ROOT / "source/work/camera_long_cut.mp4")
    parser.add_argument("--screen-out", type=Path, default=ROOT / "source/work/screen_long_cut.mp4")
    args = parser.parse_args()

    segments = load_segments(args.segments)
    camera_filter = ROOT / "source/edit/camera_long_filter.txt"
    screen_filter = ROOT / "source/edit/screen_long_filter.txt"
    write_camera_filter(segments, camera_filter)
    write_screen_filter(segments, screen_filter)

    args.camera_out.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-i",
            str(args.camera_in),
            "-filter_complex_script",
            str(camera_filter),
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(args.camera_out),
        ]
    )
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-i",
            str(args.screen_in),
            "-filter_complex_script",
            str(screen_filter),
            "-map",
            "[outv]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(args.screen_out),
        ]
    )


if __name__ == "__main__":
    main()
