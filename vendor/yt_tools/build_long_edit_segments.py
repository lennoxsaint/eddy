#!/usr/bin/env python3
"""Build long-form keep segments from the transcript pass and silence map."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path("/Users/yassybabes/YouTube")
SILENCE_LOG = ROOT / "source/edit/silence.log"
OUT_JSON = ROOT / "source/edit/keep_segments.long.json"
OUT_DECISIONS = ROOT / "source/edit/edit-decisions.json"
OUT_STRATEGY = ROOT / "source/edit/edit-strategy.md"

SILENCE_CUT_THRESHOLD = 0.50
SPEECH_PAD = 0.08
MIN_SEGMENT = 0.20

WINDOWS = [
    {"start": 164.55, "end": 186.04, "label": "strongest opening hook"},
    {"start": 280.84, "end": 337.54, "label": "trigger video proof"},
    {"start": 397.76, "end": 415.24, "label": "random mix thesis"},
    {"start": 526.54, "end": 537.37, "label": "receipts bridge"},
    {"start": 605.31, "end": 697.06, "label": "what the trigger video proved"},
    {"start": 724.99, "end": 737.08, "label": "buyer self-selected"},
    {"start": 753.12, "end": 769.07, "label": "regulated buyer context final take"},
    {"start": 776.25, "end": 780.37, "label": "small channel offer"},
    {"start": 787.54, "end": 795.08, "label": "viewer promise"},
    {"start": 814.51, "end": 824.67, "label": "seven-step promise"},
    {"start": 841.55, "end": 850.37, "label": "canonical intro recorded take"},
    {"start": 945.70, "end": 952.72, "label": "proof content beats subscribers"},
    {"start": 959.35, "end": 978.18, "label": "proof client hook final take"},
    {"start": 980.23, "end": 1100.06, "label": "content for views vs proof"},
    {"start": 1156.94, "end": 1200.88, "label": "proof removes buyer risk"},
    {"start": 1222.39, "end": 1317.19, "label": "content as targeted bait"},
    {"start": 1329.40, "end": 1421.01, "label": "client found me"},
    {"start": 1427.90, "end": 1438.09, "label": "buyer type"},
    {"start": 1441.67, "end": 1482.41, "label": "first message intent"},
    {"start": 1589.64, "end": 1646.97, "label": "warm call benefit"},
    {"start": 1672.76, "end": 2061.96, "label": "show the system, don't pitch"},
    {"start": 2119.92, "end": 2410.66, "label": "unfair overlap"},
    {"start": 2425.20, "end": 2613.09, "label": "why random skills mattered"},
    {"start": 2653.72, "end": 2711.88, "label": "calculated free work"},
    {"start": 2793.28, "end": 2818.07, "label": "readiness pack"},
    {"start": 2821.91, "end": 2854.94, "label": "specific proof for this buyer"},
    {"start": 2876.75, "end": 2908.94, "label": "reduce perceived risk"},
    {"start": 2919.08, "end": 2955.89, "label": "team-call prep"},
    {"start": 2968.32, "end": 3028.28, "label": "demo and proof"},
    {"start": 3045.78, "end": 3077.58, "label": "define success"},
    {"start": 3100.94, "end": 3109.70, "label": "money comes after proof"},
    {"start": 3127.40, "end": 3132.16, "label": "who says price first"},
    {"start": 3149.28, "end": 3154.02, "label": "price-first lesson"},
    {"start": 3230.95, "end": 3250.85, "label": "let them bring up money"},
    {"start": 3259.69, "end": 3342.71, "label": "shape of the deal"},
    {"start": 3447.02, "end": 3479.95, "label": "proof relationship money"},
    {"start": 3504.60, "end": 3509.52, "label": "contract hook final take"},
    {"start": 3527.66, "end": 3567.16, "label": "contract first draft warning"},
    {"start": 3615.39, "end": 3628.38, "label": "three contract checks"},
    {"start": 3634.94, "end": 3666.22, "label": "ownership/IP"},
    {"start": 3677.74, "end": 3726.08, "label": "payment terms"},
    {"start": 3736.40, "end": 3807.60, "label": "what happens after"},
    {"start": 3823.02, "end": 3852.85, "label": "negotiation lesson"},
    {"start": 3871.02, "end": 3884.89, "label": "signed and landed"},
    {"start": 3912.91, "end": 3982.34, "label": "closing thesis"},
    {"start": 3999.86, "end": 4035.16, "label": "make proof content"},
    {"start": 4135.90, "end": 4191.65, "label": "share wins and losses"},
    {"start": 4228.49, "end": 4279.23, "label": "operator path recap"},
    {"start": 4325.75, "end": 4339.32, "label": "final CTA"},
]

REMOVED_NOTES = [
    "Dropped early hook labels and repeated hook takes, keeping the strongest recorded opening.",
    "Dropped explicit Hook for Short / Book4Short markers from the long video.",
    "Dropped 'Delete that last sentence, Jazzy' and the surrounding discarded CTA attempt.",
    "Preserved swear words and personality moments where they support the point.",
    "Preserved the recorded canonical intro without inventing unrecorded wording.",
]


def parse_silences() -> list[tuple[float, float, float]]:
    starts: list[float] = []
    intervals: list[tuple[float, float, float]] = []
    for line in SILENCE_LOG.read_text(errors="ignore").splitlines():
        start_match = re.search(r"silence_start: ([0-9.]+)", line)
        if start_match:
            starts.append(float(start_match.group(1)))
            continue
        end_match = re.search(
            r"silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)", line
        )
        if end_match and starts:
            end = float(end_match.group(1))
            duration = float(end_match.group(2))
            start = starts.pop(0)
            intervals.append((start, end, duration))
    return intervals


def split_window(window: dict[str, float | str], silences: list[tuple[float, float, float]]):
    chunks = [(float(window["start"]), float(window["end"]))]
    for silence_start, silence_end, duration in silences:
        if duration < SILENCE_CUT_THRESHOLD:
            continue
        next_chunks = []
        for start, end in chunks:
            if silence_end <= start or silence_start >= end:
                next_chunks.append((start, end))
                continue
            left_end = max(start, silence_start + SPEECH_PAD)
            right_start = min(end, silence_end - SPEECH_PAD)
            if left_end - start >= MIN_SEGMENT:
                next_chunks.append((start, left_end))
            if end - right_start >= MIN_SEGMENT:
                next_chunks.append((right_start, end))
        chunks = next_chunks
    return chunks


def main() -> None:
    silences = parse_silences()
    segments = []
    for window in WINDOWS:
        for start, end in split_window(window, silences):
            segments.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "source_label": window["label"],
                }
            )

    output_duration = sum(segment["end"] - segment["start"] for segment in segments)
    OUT_JSON.write_text(json.dumps({"segments": segments}, indent=2), encoding="utf-8")

    decisions = {
        "source_duration_seconds": 4343.40,
        "estimated_long_duration_seconds": round(output_duration, 2),
        "silence_cut_threshold_seconds": SILENCE_CUT_THRESHOLD,
        "windows": WINDOWS,
        "removed_notes": REMOVED_NOTES,
    }
    OUT_DECISIONS.write_text(json.dumps(decisions, indent=2), encoding="utf-8")

    strategy = [
        "# Long-form edit strategy",
        "",
        "Goal: create a clean Descript-ready long edit from the raw camera and screen recordings without spending Underlord credits.",
        "",
        "Rules applied:",
        *[f"- {note}" for note in REMOVED_NOTES],
        f"- Shortened detected silent gaps longer than {SILENCE_CUT_THRESHOLD:.2f}s inside selected takes.",
        "",
        f"Estimated cut duration: {output_duration / 60:.2f} minutes.",
    ]
    OUT_STRATEGY.write_text("\n".join(strategy) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_JSON}")
    print(f"Estimated duration: {output_duration / 60:.2f} minutes")
    print(f"Segments: {len(segments)}")


if __name__ == "__main__":
    main()
