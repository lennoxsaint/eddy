"""Pack word-level transcript into phrase lines + silence/gap map.

takes_packed.md: `[start-end] phrase text` per line, breaking on silence >= 0.5s.
silence-map.json: every inter-word gap >= 0.35s with location context (transcript-derived).
audio-silence.json: AUDIO-TRUTH silent spans from ffmpeg silencedetect on the WAV. This is
  independent of the transcript and is what catches "mouth moving, no sound" spans that
  produce no transcribed words.
"""

from __future__ import annotations

import json
import re
import subprocess
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


def detect_audio_silence(wav: Path, noise_db: float = -34.0, min_d: float = 0.30) -> list[dict]:
    """Audio-truth silent spans via ffmpeg silencedetect. Returns [{start, end, dur}].

    silencedetect emits `silence_start: T` / `silence_end: T | silence_duration: D`.
    These spans are genuinely below the noise floor (no speech), so the surrounding
    words sit outside [start, end] — safe to remove without clipping speech.
    """
    from eddy.media.ffmpeg import FFMPEG

    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(wav),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_d}", "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800,
    )
    spans: list[dict] = []
    start: float | None = None
    for ln in proc.stderr.splitlines():
        ms = re.search(r"silence_start: (-?[\d.]+)", ln)
        if ms:
            start = float(ms.group(1))
            continue
        me = re.search(r"silence_end: (-?[\d.]+)", ln)
        if me and start is not None:
            end = float(me.group(1))
            if end > start:
                spans.append({"start": round(max(0.0, start), 3), "end": round(end, 3), "dur": round(end - start, 3)})
            start = None
    return spans


def build_audio_silence_map(run_dir: Path, noise_db: float = -34.0) -> Path:
    """Compute + cache the audio-truth silence map from transcript/audio-16k.wav."""
    tdir = Path(run_dir) / "transcript"
    wav = tdir / "audio-16k.wav"
    out = tdir / "audio-silence.json"
    spans = detect_audio_silence(wav, noise_db=noise_db) if wav.exists() else []
    out.write_text(json.dumps(spans, indent=1))
    return out


def phrases(run_dir: Path) -> list[dict]:
    return json.loads((Path(run_dir) / "transcript" / "phrases.json").read_text())


def silence_map(run_dir: Path) -> list[dict]:
    return json.loads((Path(run_dir) / "transcript" / "silence-map.json").read_text())


def audio_silence_map(run_dir: Path) -> list[dict]:
    """Audio-truth silent spans [{start, end, dur}]; empty list if not yet built."""
    p = Path(run_dir) / "transcript" / "audio-silence.json"
    return json.loads(p.read_text()) if p.exists() else []
