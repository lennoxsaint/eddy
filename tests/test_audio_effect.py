import math
import importlib.util
import shutil
import subprocess
import wave
from pathlib import Path

from eddy.audio_effect import EffectCalibration, evaluate_effect_survival


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
