#!/usr/bin/env python3
"""Apply explicit retake-removal and force-keep ranges to long keep segments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path("/Users/yassybabes/YouTube")
MIN_SEGMENT = 0.08


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sort_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(segments, key=lambda item: (float(item["start"]), float(item["end"])))


def overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


def apply_force_keep(
    segments: list[dict[str, Any]], force_ranges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    current = sort_segments(segments)
    for force in force_ranges:
        start = float(force["start"])
        end = float(force["end"])
        label = str(force.get("label", "force keep"))
        next_segments: list[dict[str, Any]] = []
        inserted = False
        for segment in current:
            seg_start = float(segment["start"])
            seg_end = float(segment["end"])
            if overlap(seg_start, seg_end, start, end):
                if not inserted:
                    next_segments.append(
                        {
                            "start": round(start, 3),
                            "end": round(end, 3),
                            "source_label": label,
                        }
                    )
                    inserted = True
                continue
            next_segments.append(segment)
        if not inserted:
            next_segments.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "source_label": label,
                }
            )
        current = sort_segments(next_segments)
    return current


def subtract_range(
    segments: list[dict[str, Any]], remove: dict[str, Any]
) -> list[dict[str, Any]]:
    start = float(remove["start"])
    end = float(remove["end"])
    label = str(remove.get("label", "retake removal"))
    next_segments: list[dict[str, Any]] = []
    for segment in segments:
        seg_start = float(segment["start"])
        seg_end = float(segment["end"])
        if not overlap(seg_start, seg_end, start, end):
            next_segments.append(segment)
            continue
        if start - seg_start >= MIN_SEGMENT:
            left = dict(segment)
            left["end"] = round(start, 3)
            next_segments.append(left)
        if seg_end - end >= MIN_SEGMENT:
            right = dict(segment)
            right["start"] = round(end, 3)
            right["source_label"] = f"{segment.get('source_label', '')} after {label}".strip()
            next_segments.append(right)
    return sort_segments(next_segments)


def validate(segments: list[dict[str, Any]]) -> None:
    previous_end = -1.0
    for idx, segment in enumerate(sort_segments(segments)):
        start = float(segment["start"])
        end = float(segment["end"])
        if end <= start:
            raise ValueError(f"Segment {idx} is non-positive: {segment}")
        if start < previous_end:
            raise ValueError(f"Segment {idx} overlaps previous segment: {segment}")
        previous_end = end


def output_duration(segments: list[dict[str, Any]]) -> float:
    return sum(float(item["end"]) - float(item["start"]) for item in segments)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "source/edit/keep_segments.long.json")
    parser.add_argument("--overlay", type=Path, default=ROOT / "source/edit/retake_removals.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "source/edit/keep_segments.long.retake_qa.json",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=ROOT / "source/edit/retake-removal-qa-log.md",
    )
    args = parser.parse_args()

    original_payload = load_json(args.input)
    overlay = load_json(args.overlay)
    segments = sort_segments(original_payload["segments"])
    before_duration = output_duration(segments)

    segments = apply_force_keep(segments, overlay.get("force_keep_ranges", []))
    for removal in overlay.get("remove_ranges", []):
        segments = subtract_range(segments, removal)

    validate(segments)
    after_duration = output_duration(segments)

    payload = {
        "source": str(args.input),
        "overlay": str(args.overlay),
        "segments": segments,
        "duration_before_seconds": round(before_duration, 3),
        "duration_after_seconds": round(after_duration, 3),
        "duration_delta_seconds": round(after_duration - before_duration, 3),
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Retake Removal QA Log",
        "",
        "## Batch 1 - First Three Minutes",
        "",
        f"- Source keep list: `{args.input}`",
        f"- Revised keep list: `{args.output}`",
        f"- Duration before: {before_duration:.3f}s",
        f"- Duration after batch 1: {after_duration:.3f}s",
        f"- Delta: {after_duration - before_duration:.3f}s",
        "",
        "| Reviewed Range | Issue Found | Removed Raw Range | Kept Raw Range | Reason | Confidence |",
        "|---|---|---:|---|---|---:|",
    ]
    for removal in overlay.get("remove_ranges", []):
        reviewed_range = removal.get("reviewed_range")
        if not reviewed_range:
            reviewed_range = (
                "opening/first 3 minutes"
                if float(removal["start"]) < 1236.0
                else "full timeline retake sweep"
            )
        lines.append(
            f"| {reviewed_range} | "
            f"{removal['issue']} | "
            f"{float(removal['start']):.3f}-{float(removal['end']):.3f} | "
            f"{removal['kept_range']} | "
            f"{removal['label']} | "
            f"{float(removal['confidence']):.2f} |"
        )
    lines.extend(
        [
            "",
            "## Force-Keep Repairs",
            "",
            "| Raw Range | Reason | Confidence |",
            "|---:|---|---:|",
        ]
    )
    for force in overlay.get("force_keep_ranges", []):
        lines.append(
            f"| {float(force['start']):.3f}-{float(force['end']):.3f} | "
            f"{force['reason']} | "
            f"{float(force['confidence']):.2f} |"
        )
    lines.append("")
    args.log.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {args.output}")
    print(f"Wrote {args.log}")
    print(f"Duration delta: {after_duration - before_duration:.3f}s")


if __name__ == "__main__":
    main()
