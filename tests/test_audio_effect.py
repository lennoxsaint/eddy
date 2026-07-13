import importlib.util
import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from eddy.audio_effect import (
    EffectCalibration,
    evaluate_effect_survival,
    restore_effect_cache,
    store_effect_cache,
)


ROOT = Path(__file__).resolve().parents[1]


def load_descript_script():
    spec = importlib.util.spec_from_file_location(
        "descript_studio_sound",
        ROOT / "scripts" / "descript_studio_sound.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_wav(path: Path, samples: list[float], rate: int = 16_000) -> None:
    pcm = bytearray()
    for sample in samples:
        value = max(-32768, min(32767, int(sample * 32767)))
        pcm.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(pcm))


def fixture_samples(count: int = 16_000) -> list[float]:
    return [
        0.45 * math.sin(2 * math.pi * 220 * index / 16_000)
        + 0.08 * math.sin(2 * math.pi * 2_300 * index / 16_000)
        for index in range(count)
    ]


def write_green_provider_receipts(path: Path, artifact: str = "long-primary.mp4") -> None:
    rows = [
        {
            "event": "descript_provider",
            "artifact": artifact,
            "provider": "descript_api",
            "project_id": "project-1",
            "composition_id": "composition-1",
            "access_level": "private",
        },
        {
            "event": "descript_effect_survival",
            "artifact": artifact,
            "status": "pass",
            "blockers": [],
            "metrics": {"normalized_correlation": 0.84},
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def test_effect_cache_restores_only_exact_green_input(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    input_media = tmp_path / "input.mp4"
    output_media = tmp_path / "output.mp4"
    receipts = tmp_path / "provider-receipts.jsonl"
    restored = tmp_path / "restored.mp4"
    input_media.write_bytes(b"deterministic pre-audio render")
    output_media.write_bytes(b"same video with real Studio Sound")
    write_green_provider_receipts(receipts)

    stored = store_effect_cache(
        cache,
        input_media,
        output_media,
        receipts,
        "long-primary.mp4",
    )
    hit = restore_effect_cache(cache, input_media, restored)

    assert hit == stored
    assert restored.read_bytes() == output_media.read_bytes()

    changed_input = tmp_path / "changed.mp4"
    changed_input.write_bytes(b"a different edit")
    assert restore_effect_cache(cache, changed_input, tmp_path / "miss.mp4") is None


def test_effect_cache_fails_closed_on_bad_proof_or_tampering(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    input_media = tmp_path / "input.mp4"
    output_media = tmp_path / "output.mp4"
    receipts = tmp_path / "provider-receipts.jsonl"
    input_media.write_bytes(b"input")
    output_media.write_bytes(b"cleaned")
    receipts.write_text(
        json.dumps(
            {
                "event": "descript_effect_survival",
                "artifact": "long-primary.mp4",
                "status": "failed",
                "blockers": ["descript_effect_not_rendered"],
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="descript_cache_green_proof_required"):
        store_effect_cache(cache, input_media, output_media, receipts, "long-primary.mp4")

    write_green_provider_receipts(receipts)
    manifest = store_effect_cache(
        cache,
        input_media,
        output_media,
        receipts,
        "long-primary.mp4",
    )
    cached_media = cache / str(manifest["input_sha256"]) / "output.mp4"
    cached_media.write_bytes(b"tampered")

    assert restore_effect_cache(cache, input_media, tmp_path / "restored.mp4") is None


def test_identical_export_fails_effect_survival(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    exported = tmp_path / "exported.wav"
    write_wav(source, fixture_samples())
    exported.write_bytes(source.read_bytes())

    result = evaluate_effect_survival(source, exported, EffectCalibration.default())

    assert result.passed is False
    assert "descript_effect_not_rendered" in result.blockers
    assert result.metrics["normalized_correlation"] > 0.9999


def test_gain_only_export_does_not_count_as_studio_sound(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    exported = tmp_path / "exported.wav"
    samples = fixture_samples()
    write_wav(source, samples)
    write_wav(exported, [sample * 0.8 for sample in samples])

    result = evaluate_effect_survival(source, exported, EffectCalibration.default())

    assert result.passed is False
    assert "descript_effect_not_rendered" in result.blockers


def test_codec_roundtrip_without_effect_does_not_count_as_studio_sound(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        return
    source = tmp_path / "source.wav"
    encoded = tmp_path / "encoded.m4a"
    decoded = tmp_path / "decoded.wav"
    write_wav(source, fixture_samples(64_000), rate=16_000)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-c:a", "aac", str(encoded)],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(encoded), "-ac", "1", "-ar",
            "16000", "-c:a", "pcm_s16le", str(decoded),
        ],
        check=True,
    )

    result = evaluate_effect_survival(source, decoded, EffectCalibration.default())

    assert result.passed is False
    assert "descript_effect_not_rendered" in result.blockers


def test_changed_same_duration_audio_passes_effect_survival(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.wav"
    exported = tmp_path / "exported.wav"
    samples = fixture_samples()
    write_wav(source, samples)
    write_wav(exported, [sample - 0.08 * math.sin(2 * math.pi * 2_300 * i / 16_000) for i, sample in enumerate(samples)])
    monkeypatch.setattr(
        "eddy.audio_effect.reverb_tail_metrics",
        lambda path: {"measurable": True, "echo_score": 0.02},
    )

    result = evaluate_effect_survival(source, exported, EffectCalibration.default())

    assert result.passed is True
    assert result.blockers == ()
    assert result.metrics["duration_delta_s"] == 0.0


def test_changed_audio_is_not_blocked_by_uncalibrated_echo_diagnostic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.wav"
    exported = tmp_path / "exported.wav"
    samples = fixture_samples()
    write_wav(source, samples)
    write_wav(exported, [sample - 0.08 * math.sin(2 * math.pi * 2_300 * i / 16_000) for i, sample in enumerate(samples)])
    monkeypatch.setattr(
        "eddy.audio_effect.reverb_tail_metrics",
        lambda path: {"measurable": True, "echo_score": 0.68},
    )

    result = evaluate_effect_survival(source, exported, EffectCalibration.default())

    assert result.passed is True
    assert result.blockers == ()
    assert result.metrics["echo_score"] == 0.68


def test_duration_shift_and_malformed_audio_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    short = tmp_path / "short.wav"
    malformed = tmp_path / "malformed.wav"
    write_wav(source, fixture_samples(64_000))
    write_wav(short, fixture_samples(32_000))
    malformed.write_text("not audio")

    shifted = evaluate_effect_survival(source, short, EffectCalibration.default())
    invalid = evaluate_effect_survival(source, malformed, EffectCalibration.default())

    assert "descript_duration_parity_failed" in shifted.blockers
    assert invalid.blockers == ("descript_export_invalid",)


def test_polarity_inversion_is_not_mistaken_for_studio_sound(tmp_path: Path, monkeypatch) -> None:
    samples = fixture_samples(64_000)
    source = tmp_path / "source.wav"
    exported = tmp_path / "inverted.wav"
    write_wav(source, samples)
    write_wav(exported, [-sample for sample in samples])
    monkeypatch.setattr(
        "eddy.audio_effect.reverb_tail_metrics",
        lambda path: {"measurable": True, "echo_score": 0.01},
    )

    result = evaluate_effect_survival(source, exported, EffectCalibration.default())

    assert result.passed is False
    assert "descript_effect_not_rendered" in result.blockers


def test_unmeasurable_echo_diagnostic_does_not_block_proven_effect(
    tmp_path: Path,
    monkeypatch,
) -> None:
    samples = fixture_samples(64_000)
    source = tmp_path / "source.wav"
    exported = tmp_path / "changed.wav"
    write_wav(source, samples)
    write_wav(
        exported,
        [sample * (0.7 if index % 2 else 0.3) for index, sample in enumerate(samples)],
    )
    monkeypatch.setattr(
        "eddy.audio_effect.reverb_tail_metrics",
        lambda path: {"measurable": False, "echo_score": 0.0},
    )

    result = evaluate_effect_survival(source, exported, EffectCalibration.default())

    assert result.passed is True
    assert result.blockers == ()
    assert result.metrics["echo_measurable"] == 0.0


def test_descript_prompt_always_requests_full_intensity_on_every_clip() -> None:
    descript = load_descript_script()

    prompt = descript.studio_sound_prompt(100)

    assert "every clip" in prompt
    assert "100% intensity" in prompt


def test_unchanged_descript_export_retries_once_and_uses_green_result(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    descript = load_descript_script()
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    calls: list[Path] = []
    survival_results = iter([False, True])

    def fake_studio_sound(
        wav: Path,
        out: Path,
        token: str,
        intensity: int,
    ) -> Path:
        calls.append(out)
        out.write_bytes(b"cleaned")
        return out

    monkeypatch.setattr(descript, "studio_sound", fake_studio_sound)
    monkeypatch.setattr(descript, "parity_ok", lambda source, cleaned: True)
    monkeypatch.setattr(
        descript,
        "effect_survival_ok",
        lambda source, cleaned, work: next(survival_results),
    )

    result = descript.studio_sound_with_effect_retry(source, tmp_path / "work", "token", 100)

    assert result == tmp_path / "work/retry-2/descript-studio-sound.m4a"
    assert calls == [
        tmp_path / "work/descript-studio-sound.m4a",
        tmp_path / "work/retry-2/descript-studio-sound.m4a",
    ]
    assert '"event": "descript_effect_retry"' in capsys.readouterr().err


def test_descript_effect_retry_stops_after_second_unchanged_export(
    tmp_path: Path,
    monkeypatch,
) -> None:
    descript = load_descript_script()
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    calls: list[Path] = []

    def fake_studio_sound(
        wav: Path,
        out: Path,
        token: str,
        intensity: int,
    ) -> Path:
        calls.append(out)
        out.write_bytes(b"cleaned")
        return out

    monkeypatch.setattr(descript, "studio_sound", fake_studio_sound)
    monkeypatch.setattr(descript, "parity_ok", lambda source, cleaned: True)
    monkeypatch.setattr(
        descript,
        "effect_survival_ok",
        lambda source, cleaned, work: False,
    )

    result = descript.studio_sound_with_effect_retry(source, tmp_path / "work", "token", 100)

    assert result is None
    assert len(calls) == 2


def test_descript_voice_consent_is_terminal_and_not_retried(tmp_path: Path, monkeypatch) -> None:
    descript = load_descript_script()
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    calls = 0

    def blocked_studio_sound(wav: Path, out: Path, token: str, intensity: int) -> Path:
        nonlocal calls
        calls += 1
        raise RuntimeError("descript_voice_consent_required")

    monkeypatch.setattr(descript, "studio_sound", blocked_studio_sound)
    with pytest.raises(RuntimeError, match="descript_voice_consent_required"):
        descript.studio_sound_with_effect_retry(source, tmp_path / "work", "token", 100)
    assert calls == 1


def test_descript_agent_response_detects_voice_consent_blocker() -> None:
    descript = load_descript_script()
    response = "The speaker has no verified voice consent (`no_verified_consent`)."
    assert descript.agent_terminal_blocker(response) == "descript_voice_consent_required"


def test_descript_provider_timeout_retries_once(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    descript = load_descript_script()
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    calls: list[Path] = []

    def fake_studio_sound(
        wav: Path,
        out: Path,
        token: str,
        intensity: int,
    ) -> Path:
        calls.append(out)
        if len(calls) == 1:
            raise RuntimeError("descript_job_timeout:job-id")
        out.write_bytes(b"cleaned")
        return out

    monkeypatch.setattr(descript, "studio_sound", fake_studio_sound)
    monkeypatch.setattr(descript, "parity_ok", lambda source, cleaned: True)
    monkeypatch.setattr(descript, "effect_survival_ok", lambda source, cleaned, work: True)
    monkeypatch.setattr(descript.time, "sleep", lambda seconds: None)

    result = descript.studio_sound_with_effect_retry(source, tmp_path / "work", "token", 100)

    assert result == tmp_path / "work/retry-2/descript-studio-sound.m4a"
    assert len(calls) == 2
    assert '"event": "descript_provider_retry"' in capsys.readouterr().err


def test_descript_provider_retries_two_transient_failures_before_success(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    descript = load_descript_script()
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    calls: list[Path] = []
    sleeps: list[float] = []

    def fake_studio_sound(
        wav: Path,
        out: Path,
        token: str,
        intensity: int,
    ) -> Path:
        calls.append(out)
        if len(calls) < 3:
            raise RuntimeError(f"descript_job_failed:job-{len(calls)}:error")
        out.write_bytes(b"cleaned")
        return out

    monkeypatch.setattr(descript, "studio_sound", fake_studio_sound)
    monkeypatch.setattr(descript, "parity_ok", lambda source, cleaned: True)
    monkeypatch.setattr(descript, "effect_survival_ok", lambda source, cleaned, work: True)
    monkeypatch.setattr(descript.time, "sleep", sleeps.append)

    result = descript.studio_sound_with_effect_retry(source, tmp_path / "work", "token", 100)

    assert result == tmp_path / "work/retry-3/descript-studio-sound.m4a"
    assert len(calls) == 3
    assert sleeps == [descript.PROVIDER_RETRY_DELAY_S, descript.PROVIDER_RETRY_DELAY_S * 2]
    assert capsys.readouterr().err.count('"event": "descript_provider_retry"') == 2


def test_descript_failed_job_logs_sanitized_provider_message(
    monkeypatch,
    capsys,
) -> None:
    descript = load_descript_script()
    monkeypatch.setattr(
        descript,
        "api",
        lambda method, path, token, payload: {
            "job_state": "stopped",
            "result": {"status": "error", "error_message": "Job failed unexpectedly."},
        },
    )

    with pytest.raises(RuntimeError, match="descript_job_failed:job-id:error"):
        descript.wait_job("job-id", "token")

    stderr = capsys.readouterr().err
    assert '"event": "descript_job_failed"' in stderr
    assert '"error_message": "Job failed unexpectedly."' in stderr


def test_descript_auth_failure_does_not_retry(tmp_path: Path, monkeypatch) -> None:
    descript = load_descript_script()
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    calls = 0

    def fake_studio_sound(
        wav: Path,
        out: Path,
        token: str,
        intensity: int,
    ) -> Path:
        nonlocal calls
        calls += 1
        raise RuntimeError("descript_api_failed:/jobs/agent:401")

    monkeypatch.setattr(descript, "studio_sound", fake_studio_sound)

    with pytest.raises(RuntimeError, match="descript_api_failed"):
        descript.studio_sound_with_effect_retry(source, tmp_path / "work", "token", 100)

    assert calls == 1
