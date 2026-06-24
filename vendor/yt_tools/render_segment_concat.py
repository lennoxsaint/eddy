#!/usr/bin/env python3
"""Render edited videos by extracting segments and concatenating them."""

from __future__ import annotations

import os
import argparse
import concurrent.futures
import json
import shlex
import subprocess
from pathlib import Path


ROOT = Path(os.environ.get("EDDY_YT_TOOLS_ROOT", "~/YouTube")).expanduser()
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def segment_cmd(
    input_path: Path,
    output_path: Path,
    start: float,
    end: float,
    kind: str,
    accurate_seek: bool = False,
    seek_preroll: float = 2.0,
) -> list[str]:
    duration = max(0.05, end - start)
    seek_start = max(0.0, start - seek_preroll) if accurate_seek else start
    output_seek = start - seek_start if accurate_seek else 0.0
    cmd = [
        FFMPEG,
        "-y",
        "-hide_banner",
    ]
    cmd.extend(["-ss", f"{seek_start:.3f}"])
    cmd.extend(
        [
        "-i",
        str(input_path),
        ]
    )
    if kind == "screen":
        cmd.extend(
            [
                "-f",
                "lavfi",
                "-t",
                f"{duration:.3f}",
                "-i",
                "anullsrc=channel_layout=mono:sample_rate=48000",
            ]
        )
    if accurate_seek and output_seek > 0:
        cmd.extend(["-ss", f"{output_seek:.3f}"])
    cmd.extend(
        [
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        ]
    )
    if kind == "screen":
        cmd.extend(["-map", "1:a:0"])
    else:
        cmd.extend(["-map", "0:a:0"])
    cmd.extend(
        [
        "-vf",
        "fps=30,setpts=PTS-STARTPTS",
        "-c:v",
        "h264_videotoolbox",
        "-allow_sw",
        "1",
        "-pix_fmt",
        "yuv420p",
        ]
    )
    if kind == "camera":
        cmd.extend(["-b:v", "7000k", "-c:a", "aac", "-b:a", "160k"])
    else:
        cmd.extend(["-b:v", "10000k", "-c:a", "aac", "-b:a", "32k"])
    cmd.extend(["-movflags", "+faststart", str(output_path)])
    return cmd


def render_one(args: tuple[int, dict[str, float], Path, Path, str, bool, bool, float]) -> Path:
    idx, segment, input_path, out_dir, kind, accurate_seek, force, seek_preroll = args
    output_path = out_dir / f"{idx:04d}.mp4"
    if not force and output_path.exists() and output_path.stat().st_size > 1024:
        return output_path
    run(
        segment_cmd(
            input_path,
            output_path,
            segment["start"],
            segment["end"],
            kind,
            accurate_seek=accurate_seek,
            seek_preroll=seek_preroll,
        )
    )
    return output_path


def concat_list(paths: list[Path], list_path: Path) -> None:
    lines = [f"file {shlex.quote(str(path))}" for path in paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def concat(paths: list[Path], list_path: Path, output_path: Path) -> None:
    concat_list(paths, list_path)
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments", type=Path, default=ROOT / "source/edit/keep_segments.long.json")
    parser.add_argument("--kind", choices=["camera", "screen"], required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--concat-list", type=Path)
    parser.add_argument("--accurate-seek", action="store_true")
    parser.add_argument("--seek-preroll", type=float, default=2.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    segments = json.loads(args.segments.read_text(encoding="utf-8"))["segments"]
    if args.limit:
        segments = segments[: args.limit]

    input_path = ROOT / ("source/raw/camera.mp4" if args.kind == "camera" else "source/raw/screen.mp4")
    out_dir = args.out_dir or ROOT / f"source/work/{args.kind}_long_segments"
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = [
        (
            idx,
            segment,
            input_path,
            out_dir,
            args.kind,
            args.accurate_seek,
            args.force,
            args.seek_preroll,
        )
        for idx, segment in enumerate(segments)
    ]
    paths: list[Path] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for completed, path in enumerate(pool.map(render_one, jobs), start=1):
            paths.append(path)
            if completed % 25 == 0 or completed == len(jobs):
                print(f"{args.kind}: {completed}/{len(jobs)} segments")

    output_path = args.output or ROOT / f"source/work/{args.kind}_long_cut.mp4"
    list_path = args.concat_list or ROOT / f"source/edit/{args.kind}_long_concat.txt"
    concat(paths, list_path, output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
