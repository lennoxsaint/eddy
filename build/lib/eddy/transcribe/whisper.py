"""faster-whisper word-level transcription, cached by source hash.

Port of vendor/yt_tools/transcribe_faster_whisper.py with paths parameterized
and caching added. Audio is extracted to 16k mono WAV first (faster + stable).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from eddy.config import load_config
from eddy.loop.receipts import Receipts
from eddy.media.ffmpeg import run_ffmpeg
from eddy.runs import manifest

INITIAL_PROMPT = (
    "Vocabulary: Threadify, OpenClaw, Codex, Claude, ChatGPT, Descript, Skool, "
    "Kit, Ollama, Eddy. Book4Short means Hook for Short."
)


def transcribe_run(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    cfg = load_config()
    m = manifest(run_dir)
    receipts = Receipts(run_dir)
    out = run_dir / "transcript" / "words.json"

    if out.exists():
        cached = json.loads(out.read_text())
        if cached.get("source_sha256") == m["source_sha256"]["camera"]:
            receipts.log("transcribe", cache="hit")
            return out

    audio_source = Path(m["sources"].get("mic") or m["sources"]["camera"])
    wav = run_dir / "transcript" / "audio-16k.wav"
    if not wav.exists():
        run_ffmpeg(
            ["-i", str(audio_source), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
            run_dir=run_dir,
            receipts=receipts,
        )

    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(cfg.transcribe.model, device="auto", compute_type=cfg.transcribe.compute_type)
    segments, info = model.transcribe(
        str(wav),
        language=cfg.transcribe.language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 350},
        initial_prompt=INITIAL_PROMPT,
    )

    payload = {
        "source_sha256": m["source_sha256"]["camera"],
        "language": info.language,
        "duration": info.duration,
        "model": cfg.transcribe.model,
        "segments": [],
    }
    for segment in segments:
        payload["segments"].append(
            {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "avg_logprob": segment.avg_logprob,
                "no_speech_prob": segment.no_speech_prob,
                "words": [
                    {"start": w.start, "end": w.end, "word": w.word, "probability": w.probability}
                    for w in (segment.words or [])
                ],
            }
        )

    out.write_text(json.dumps(payload, indent=1))
    receipts.log(
        "transcribe",
        cache="miss",
        model=cfg.transcribe.model,
        audio_s=round(info.duration, 1),
        wall_s=round(time.time() - t0, 1),
        segments=len(payload["segments"]),
    )

    from eddy.transcribe.pack import build_audio_silence_map, pack_run

    pack_run(run_dir)
    build_audio_silence_map(run_dir, noise_db=cfg.gates.silence_noise_db)
    return out


def words_flat(run_dir: Path) -> list[dict]:
    """All words in order: [{start, end, word, probability}]."""
    data = json.loads((Path(run_dir) / "transcript" / "words.json").read_text())
    out: list[dict] = []
    for seg in data["segments"]:
        out.extend(seg["words"])
    return out
