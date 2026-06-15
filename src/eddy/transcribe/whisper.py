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
from eddy.runs import SourceError, manifest


def _assert_has_speech(segments: list, source) -> None:
    """No-speech is a first-class outcome: fail fast with an actionable message instead of writing
    an empty transcript that corrupts the edit loop (empty beats/phrases downstream)."""
    if not segments:
        raise SourceError(
            f"no speech detected in {source} — is this the right file? "
            "(silent video, music-only, or the wrong audio track)"
        )

def _language_note(requested: str | None, detected: str, mean_no_speech: float) -> dict | None:
    """A non-silent health check on the transcript: warn if a FORCED language disagrees with what
    Whisper detected (forcing the wrong language silently mistranscribes), or if speech is doubtful.
    Returns None when healthy."""
    notes = []
    if requested and detected and requested != detected:
        notes.append(f"forced language '{requested}' but audio detected as '{detected}' — transcript may be wrong")
    if mean_no_speech > 0.6:
        notes.append(f"high no-speech probability ({mean_no_speech:.2f}) — audio may be music/silence")
    if not notes:
        return None
    return {"requested": requested, "detected": detected, "mean_no_speech_prob": round(mean_no_speech, 3), "notes": notes}


def transcribe_run(run_dir: Path, language: str | None = None) -> Path:
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

    from eddy.privacy import is_offline

    t0 = time.time()
    # offline/airgapped: never reach HuggingFace — use only already-downloaded weights.
    model = WhisperModel(
        cfg.transcribe.model, device="auto", compute_type=cfg.transcribe.compute_type,
        local_files_only=is_offline(),
    )
    # "" (config) or None -> auto-detect; --language / config forces a specific language.
    lang = (language or cfg.transcribe.language) or None
    segments, info = model.transcribe(
        str(wav),
        language=lang,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 350},
        initial_prompt=(cfg.transcribe.vocab_prompt or None),
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

    _assert_has_speech(payload["segments"], audio_source)  # fail fast; don't cache an empty transcript
    out.write_text(json.dumps(payload, indent=1))
    segs = payload["segments"]
    mean_no_speech = sum(s["no_speech_prob"] for s in segs) / len(segs) if segs else 1.0
    # When a language is FORCED, info.language is just the forced value, so an INDEPENDENT detect
    # pass is needed for a real mismatch warning (detect_language reads ~30s — cheap, forced-only).
    detected = info.language
    if lang is not None:
        try:
            from faster_whisper.audio import decode_audio

            detected = model.detect_language(decode_audio(str(wav)))[0]
        except Exception:
            pass  # best-effort; fall back to info.language (mismatch check then no-ops)
    health = _language_note(lang, detected, mean_no_speech)
    if health is not None:
        receipts.log("transcript_health_warning", **health)
    receipts.log(
        "transcribe",
        cache="miss",
        model=cfg.transcribe.model,
        language=info.language,
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
