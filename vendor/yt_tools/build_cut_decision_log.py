#!/usr/bin/env python3
"""Create a per-cut decision log from the long keep-segment list."""

from __future__ import annotations

import os
import json
from pathlib import Path


ROOT = Path(os.environ.get("EDDY_YT_TOOLS_ROOT", "~/YouTube")).expanduser()
KEEP_PATH = ROOT / "source/edit/keep_segments.long.json"
DECISIONS_PATH = ROOT / "source/edit/edit-decisions.json"
TRANSCRIPT_PATH = ROOT / "source/edit/transcript.faster-whisper.json"
OUT_JSON = ROOT / "source/edit/cut-decision-log.json"
OUT_MD = ROOT / "source/edit/cut-decision-log.md"
SOURCE_DURATION = 4343.40


def load_transcript_snippets() -> list[dict]:
    payload = json.loads(TRANSCRIPT_PATH.read_text(encoding="utf-8"))
    return payload["segments"]


def transcript_near(start: float, end: float, snippets: list[dict]) -> str:
    text = []
    for segment in snippets:
        if segment["end"] < start - 2 or segment["start"] > end + 2:
            continue
        text.append(segment["text"])
    return " ".join(text)[:280]


def classify_cut(start: float, end: float, previous_label: str | None, next_label: str | None, text: str) -> tuple[str, float]:
    duration = end - start
    lower = text.lower()
    if duration <= 0.65:
        return "shorten word gap / remove micro-silence without clipping words", 0.92
    if "hook for short" in lower or "hook four short" in lower or "book for short" in lower:
        return "remove Hook for Short marker from long-form timeline after preserving marker for Shorts", 0.9
    if "delete that last sentence" in lower:
        return "remove explicitly discarded sentence and surrounding false start", 0.98
    if previous_label and next_label and previous_label == next_label:
        return "remove retake gap or repeated phrasing inside selected idea", 0.86
    if duration >= 20:
        return "remove unused setup, tangent, reset, or earlier take between selected best takes", 0.82
    return "remove pause, reset, filler, or non-final take between selected transcript spans", 0.84


def main() -> None:
    keep_payload = json.loads(KEEP_PATH.read_text(encoding="utf-8"))
    keep = keep_payload["segments"]
    decisions = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    snippets = load_transcript_snippets()

    cuts = []
    cursor = 0.0
    previous_label: str | None = None
    for idx, segment in enumerate(keep):
        start = float(segment["start"])
        end = float(segment["end"])
        if start - cursor > 0.05:
            text = transcript_near(cursor, start, snippets)
            reason, confidence = classify_cut(cursor, start, previous_label, segment.get("source_label"), text)
            cuts.append(
                {
                    "cut_index": len(cuts) + 1,
                    "start": round(cursor, 3),
                    "end": round(start, 3),
                    "duration": round(start - cursor, 3),
                    "reason": reason,
                    "confidence": confidence,
                    "applies_to": ["camera", "screen", "audio"],
                    "near_transcript": text,
                }
            )
        cursor = max(cursor, end)
        previous_label = segment.get("source_label")
    if SOURCE_DURATION - cursor > 0.05:
        text = transcript_near(cursor, SOURCE_DURATION, snippets)
        reason, confidence = classify_cut(cursor, SOURCE_DURATION, previous_label, None, text)
        cuts.append(
            {
                "cut_index": len(cuts) + 1,
                "start": round(cursor, 3),
                "end": SOURCE_DURATION,
                "duration": round(SOURCE_DURATION - cursor, 3),
                "reason": reason,
                "confidence": confidence,
                "applies_to": ["camera", "screen", "audio"],
                "near_transcript": text,
            }
        )

    output = {
        "source_duration_seconds": SOURCE_DURATION,
        "keep_segments": len(keep),
        "cut_count": len(cuts),
        "cut_duration_seconds": round(sum(c["duration"] for c in cuts), 3),
        "estimated_output_seconds": round(sum(float(s["end"]) - float(s["start"]) for s in keep), 3),
        "rules": decisions.get("removed_notes", []),
        "cuts": cuts,
    }
    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")

    lines = [
        "# Cut decision log",
        "",
        f"- Source duration: {SOURCE_DURATION:.2f}s",
        f"- Keep segments: {len(keep)}",
        f"- Cuts: {len(cuts)}",
        f"- Cut duration: {output['cut_duration_seconds']:.2f}s",
        f"- Estimated output duration: {output['estimated_output_seconds']:.2f}s",
        "",
        "| # | Start | End | Reason | Confidence |",
        "|---:|---:|---:|---|---:|",
    ]
    for cut in cuts:
        lines.append(
            f"| {cut['cut_index']} | {cut['start']:.3f} | {cut['end']:.3f} | {cut['reason']} | {cut['confidence']:.2f} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    print(f"Cuts: {len(cuts)}")


if __name__ == "__main__":
    main()
