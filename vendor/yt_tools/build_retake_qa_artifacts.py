#!/usr/bin/env python3
"""Create focused QA clips and a manifest for retake-removal joins."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path("/Users/yassybabes/YouTube")
FFMPEG = "/Users/yassybabes/.homebrew/bin/ffmpeg"
FFPROBE = "/Users/yassybabes/.homebrew/bin/ffprobe"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_time(seconds: float) -> str:
    minutes, sec = divmod(max(0.0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:05.2f}"
    return f"{minutes:d}:{sec:05.2f}"


def word_text_near(words: list[dict[str, Any]], start: float, end: float) -> str:
    selected = [
        str(word["word"]).strip()
        for word in words
        if float(word["end"]) >= start and float(word["start"]) <= end
    ]
    return " ".join(selected).replace(" ,", ",").strip()


def transcript_words(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    words: list[dict[str, Any]] = []
    for segment in payload["segments"]:
        for word in segment.get("words", []):
            if "start" not in word or "end" not in word:
                continue
            words.append(
                {
                    "start": float(word["start"]),
                    "end": float(word["end"]),
                    "word": str(word["word"]),
                }
            )
    return sorted(words, key=lambda item: (float(item["start"]), float(item["end"])))


def raw_to_output_map(segments: list[dict[str, Any]]) -> list[dict[str, float]]:
    output_cursor = 0.0
    mapped: list[dict[str, float]] = []
    for segment in sorted(segments, key=lambda item: (float(item["start"]), float(item["end"]))):
        start = float(segment["start"])
        end = float(segment["end"])
        mapped.append(
            {
                "raw_start": start,
                "raw_end": end,
                "out_start": output_cursor,
                "out_end": output_cursor + (end - start),
            }
        )
        output_cursor += end - start
    return mapped


def output_time_for_raw_boundary(mapped: list[dict[str, float]], raw_time: float) -> float | None:
    tolerance = 0.012
    for segment in mapped:
        if abs(segment["raw_start"] - raw_time) <= tolerance:
            return segment["out_start"]
        if abs(segment["raw_end"] - raw_time) <= tolerance:
            return segment["out_end"]
        if segment["raw_start"] < raw_time < segment["raw_end"]:
            return segment["out_start"] + raw_time - segment["raw_start"]
    return None


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def export_clip(source: Path, output: Path, start: float, duration: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, start):.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-vf",
            "scale=1280:-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def media_duration(path: Path) -> float:
    result = subprocess.run(
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
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--segments",
        type=Path,
        default=ROOT / "source/edit/keep_segments.long.retake_qa.json",
    )
    parser.add_argument("--overlay", type=Path, default=ROOT / "source/edit/retake_removals.json")
    parser.add_argument(
        "--transcript",
        type=Path,
        default=ROOT / "source/edit/transcript.faster-whisper.json",
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=ROOT
        / "source/exports/Codex-2026-05-29-landed-2300-month-client-long-retake-qa-working.mp4",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "source/exports/qa/retake-patched-boundaries",
    )
    parser.add_argument("--handles", type=float, default=5.0)
    args = parser.parse_args()

    payload = load_json(args.segments)
    overlay = load_json(args.overlay)
    words = transcript_words(args.transcript)
    mapped = raw_to_output_map(payload["segments"])
    duration = media_duration(args.video)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    first_review = args.out_dir / "first-4-minutes-current-working.mp4"
    export_clip(args.video, first_review, 0.0, min(240.0, duration))

    rows = [
        "# Retake Join QA Clips",
        "",
        f"- Source video: `{args.video}`",
        f"- Source duration: {duration:.3f}s ({fmt_time(duration)})",
        f"- First four minutes clip: `{first_review}`",
        "",
        "| # | Label | Raw Removed | Output Join | Clip | Transcript Before | Transcript After |",
        "|---:|---|---:|---:|---|---|---|",
    ]

    for index, removal in enumerate(overlay.get("remove_ranges", []), start=1):
        raw_start = float(removal["start"])
        raw_end = float(removal["end"])
        out_time = output_time_for_raw_boundary(mapped, raw_start)
        if out_time is None:
            out_time = output_time_for_raw_boundary(mapped, raw_end)
        if out_time is None:
            clip_label = "not generated"
            clip_path = ""
            out_display = "UNKNOWN"
        else:
            clip = args.out_dir / f"{index:02d}-{str(removal['label']).replace('/', '-')}.mp4"
            export_clip(args.video, clip, out_time - args.handles, args.handles * 2)
            clip_label = str(clip)
            clip_path = f"`{clip_label}`"
            out_display = fmt_time(out_time)
        before = word_text_near(words, raw_start - 5.0, raw_start)
        after = word_text_near(words, raw_end, raw_end + 5.0)
        rows.append(
            "| "
            f"{index} | {removal['label']} | "
            f"{raw_start:.3f}-{raw_end:.3f} | {out_display} | {clip_path} | "
            f"{before} | {after} |"
        )

    manifest = args.out_dir / "manifest.md"
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Wrote {first_review}")
    print(f"Wrote {manifest}")


if __name__ == "__main__":
    main()
