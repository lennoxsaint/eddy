#!/usr/bin/env python3
"""Transcribe -> word-level JSON (deterministic).

Thin wrapper over WhisperX in the existing caption-gen venv
(`~/content-tools/caption-gen/.venv`, Python 3.12). Produces word-level timings that the beat map
and splice.py consume. Deterministic mechanics — the model does not transcribe.

Usage:
  transcribe.py --in video.mp4 --out transcript.json [--model large-v3] [--lang en]

Output JSON:
  {"language": "en", "duration": <s>,
   "words": [{"word": "Hey", "start": 0.12, "end": 0.34, "score": 0.98}, ...],
   "segments": [{"start": .., "end": .., "text": ".."}, ...]}

Notes:
- WhisperX requires Python <3.14; use the caption-gen venv (pinned 3.12).
- If the local WhisperX API differs, this is the one place to adjust — keep the output schema stable.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

VENV_PY = Path(os.path.expanduser("~/content-tools/caption-gen/.venv/bin/python"))

# Runs inside the caption-gen venv. Writes the normalized schema to the OUTPUT FILE (argv[4]),
# NOT stdout — WhisperX and its deps print progress/warnings to stdout, which would corrupt a
# stdout-parsed JSON. Writing to a file makes capture immune to that library chatter.
_RUNNER = r"""
import json, sys
import whisperx

audio_path, model_name, lang, out_path = sys.argv[1], sys.argv[2], (sys.argv[3] or None), sys.argv[4]
device = "cpu"
compute_type = "int8"

model = whisperx.load_model(model_name, device, compute_type=compute_type, language=lang)
audio = whisperx.load_audio(audio_path)
result = model.transcribe(audio, batch_size=8)
language = result.get("language", lang or "en")

align_model, meta = whisperx.load_align_model(language_code=language, device=device)
aligned = whisperx.align(result["segments"], align_model, meta, audio, device,
                         return_char_alignments=False)

words = []
for seg in aligned.get("segments", []):
    for w in seg.get("words", []):
        if w.get("start") is None or w.get("end") is None:
            continue
        words.append({
            "word": w.get("word", "").strip(),
            "start": round(float(w["start"]), 3),
            "end": round(float(w["end"]), 3),
            "score": round(float(w.get("score", 0.0)), 3),
        })

segments = [{"start": round(float(s["start"]), 3),
             "end": round(float(s["end"]), 3),
             "text": s.get("text", "").strip()}
            for s in aligned.get("segments", []) if s.get("start") is not None]

duration = words[-1]["end"] if words else (segments[-1]["end"] if segments else 0.0)
with open(out_path, "w") as fh:
    json.dump({"language": language, "duration": duration, "words": words, "segments": segments}, fh)
print("WROTE", out_path)  # marker; safe even if preceded by library chatter
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Transcribe to word-level JSON (WhisperX).")
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    if not VENV_PY.exists():
        print(f"ERROR: caption-gen venv python not found at {VENV_PY}", file=sys.stderr)
        return 2

    inp = Path(args.inp)
    if not inp.exists():
        print(f"ERROR: input not found: {inp}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".raw.json")  # runner writes here; immune to stdout chatter

    proc = subprocess.run(
        [str(VENV_PY), "-c", _RUNNER, str(inp), args.model, args.lang, str(raw)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not raw.exists():
        print(proc.stderr[-2000:], file=sys.stderr)
        print(proc.stdout[-1000:], file=sys.stderr)
        print("ERROR: whisperx transcription failed (see stderr).", file=sys.stderr)
        return 3

    try:
        data = json.loads(raw.read_text())
    except json.JSONDecodeError:
        print(raw.read_text()[-2000:], file=sys.stderr)
        print("ERROR: transcription produced non-JSON output.", file=sys.stderr)
        return 3

    out.write_text(json.dumps(data, indent=1))
    words = data.get("words", [])
    # low-confidence words are retake / mumble candidates — surface the count for the beat map.
    low_conf = sum(1 for w in words if w.get("score", 1.0) < 0.5)
    print(json.dumps({"event": "transcribed", "words": len(words),
                      "low_confidence_words": low_conf,
                      "duration": data.get("duration"), "out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
