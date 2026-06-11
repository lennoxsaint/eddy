"""Pack word-level transcript into phrase lines + silence/gap map.

takes_packed.md: `[start-end] phrase text` per line, breaking on silence >= 0.5s.
silence-map.json: every inter-word gap >= 0.35s with location context.
"""

from __future__ import annotations

import json
from pathlib import Path

PHRASE_BREAK_S = 0.5
GAP_RECORD_S = 0.35


def pack_run(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    tdir = run_dir / "transcript"
    data = json.loads((tdir / "words.json").read_text())

    words: list[dict] = []
    for seg in data["segments"]:
        words.extend(seg["words"])

    phrases: list[dict] = []
    gaps: list[dict] = []
    current: list[dict] = []

    def flush() -> None:
        if current:
            phrases.append(
                {
                    "start": round(current[0]["start"], 2),
                    "end": round(current[-1]["end"], 2),
                    "text": "".join(w["word"] for w in current).strip(),
                }
            )

    prev_end: float | None = None
    for w in words:
        if prev_end is not None:
            gap = w["start"] - prev_end
            if gap >= GAP_RECORD_S:
                gaps.append(
                    {
                        "after_s": round(prev_end, 2),
                        "gap_s": round(gap, 2),
                        "before_word": current[-1]["word"].strip() if current else (phrases[-1]["text"].split()[-1] if phrases else ""),
                        "next_word": w["word"].strip(),
                    }
                )
            if gap >= PHRASE_BREAK_S:
                flush()
                current = []
        current.append(w)
        prev_end = w["end"]
    flush()

    lines = [f"[{p['start']:.2f}-{p['end']:.2f}] {p['text']}" for p in phrases]
    (tdir / "takes_packed.md").write_text("\n".join(lines) + "\n")
    (tdir / "phrases.json").write_text(json.dumps(phrases, indent=1))
    (tdir / "silence-map.json").write_text(json.dumps(gaps, indent=1))
    return tdir / "takes_packed.md"


def phrases(run_dir: Path) -> list[dict]:
    return json.loads((Path(run_dir) / "transcript" / "phrases.json").read_text())


def silence_map(run_dir: Path) -> list[dict]:
    return json.loads((Path(run_dir) / "transcript" / "silence-map.json").read_text())
