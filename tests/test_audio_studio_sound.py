from pathlib import Path

from eddy.config import AudioConfig
from eddy.render import audio


def test_audio_config_prefers_deepfilternet_default():
    assert AudioConfig().heavy_model_preference[:2] == ["deepfilternet", "resemble-enhance"]


def test_speech_eq_includes_local_studio_sound_cleanup_when_filters_exist(monkeypatch):
    monkeypatch.setattr(
        audio._filters,
        "_available_audio_filters",
        lambda: frozenset({"afftdn", "adeclick", "deesser", "acompressor"}),
    )
    chain = audio._speech_eq(AudioConfig())
    assert "afftdn" in chain
    assert chain.count("adeclick") >= 2
    assert chain.count("deesser") >= 2
    assert "acompressor" in chain
    assert "alimiter" in chain


def test_speech_eq_skips_optional_filters_portably(monkeypatch):
    monkeypatch.setattr(audio._filters, "_available_audio_filters", lambda: frozenset())
    chain = audio._speech_eq(AudioConfig())
    assert "highpass" in chain
    assert "equalizer" in chain
    assert "alimiter" in chain
    assert "adeclick" not in chain


def test_auto_profile_names_resolve_to_known_candidates():
    cfg = AudioConfig(studio_sound_profile="auto")

    assert audio._studio_sound_profile_names(cfg) == [
        "source_reference",
        "warm_room_tame",
        "warm_deep_tame",
        "warm_click_tame",
        "warm_model_10",
        "natural_voice",
        "click_rescue",
        "broadcast_clean",
        "surgical_click_rescue",
    ]


def test_warm_room_tame_profile_is_source_first_and_warm(monkeypatch):
    monkeypatch.setattr(
        audio._filters,
        "_available_audio_filters",
        lambda: frozenset({"bass", "adeclick", "acompressor", "equalizer"}),
    )

    profile = audio.STUDIO_SOUND_PROFILES["warm_room_tame"]
    chain = audio._profile_polish_chain(profile, AudioConfig())

    assert profile.source_mode == "raw"
    assert "bass=g=" in chain
    assert "equalizer=f=900" in chain
    assert "equalizer=f=3200" in chain
    assert "afftdn" not in chain
    assert "deesser" not in chain


def test_source_reference_profile_is_do_no_harm():
    profile = audio.STUDIO_SOUND_PROFILES["source_reference"]

    assert profile.source_mode == "reference"
    assert audio._profile_polish_chain(profile, AudioConfig()) == "anull"


def test_source_reference_candidate_normalizes_loudness_without_cleanup(monkeypatch, tmp_path):
    raw = tmp_path / "raw.wav"
    raw.write_bytes(b"RIFF0000WAVE")
    seen = {}

    def fake_run_ffmpeg(argv, **kwargs):
        seen["argv"] = argv
        Path(argv[-1]).write_bytes(b"RIFF0000WAVE")

    monkeypatch.setattr(audio._candidates, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(audio._candidates, "measure_lufs", lambda _path: -14.0)
    monkeypatch.setattr(audio._candidates, "_click_event_count", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(audio._candidates, "_echo_artifact_score", lambda _path: 0.2)

    candidate = audio._render_profile_candidate(
        raw,
        raw,
        audio.STUDIO_SOUND_PROFILES["source_reference"],
        AudioConfig(),
        tmp_path,
        tmp_path,
    )

    assert "-af" in seen["argv"]
    assert "loudnorm=I=-14.0" in seen["argv"][seen["argv"].index("-af") + 1]
    assert candidate["lufs_after"] == -14.0
    assert candidate["echo_gate_pass"] is True


def test_natural_profile_avoids_echo_prone_filters(monkeypatch):
    monkeypatch.setattr(
        audio._filters,
        "_available_audio_filters",
        lambda: frozenset({"afftdn", "adeclick", "deesser", "acompressor"}),
    )

    chain = audio._profile_polish_chain(audio.STUDIO_SOUND_PROFILES["natural_voice"], AudioConfig())

    assert "adeclick" in chain
    assert "afftdn" not in chain
    assert "deesser" not in chain


def test_candidate_selector_prefers_natural_when_click_gate_passes():
    cfg = AudioConfig(echo_artifact_max_score=0.42)
    candidates = [
        {
            "profile": "natural_voice",
            "click_events_after": 5,
            "click_gate_pass": True,
            "echo_artifact_score": 0.18,
            "echo_gate_pass": True,
            "lufs_after": -14.2,
        },
        {
            "profile": "broadcast_clean",
            "click_events_after": 3,
            "click_gate_pass": True,
            "echo_artifact_score": 0.51,
            "echo_gate_pass": False,
            "lufs_after": -14.0,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=20, cfg=cfg)

    assert selected["profile"] == "natural_voice"


def test_candidate_selector_can_rescue_when_natural_fails_click_gate():
    cfg = AudioConfig(echo_artifact_max_score=0.42)
    candidates = [
        {
            "profile": "natural_voice",
            "click_events_after": 20,
            "click_gate_pass": False,
            "echo_artifact_score": 0.10,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
        {
            "profile": "click_rescue",
            "click_events_after": 4,
            "click_gate_pass": True,
            "echo_artifact_score": 0.20,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=20, cfg=cfg)

    assert selected["profile"] == "click_rescue"


def test_candidate_selector_keeps_least_processed_profile_after_click_gate_passes():
    cfg = AudioConfig(echo_artifact_max_score=0.42)
    candidates = [
        {
            "profile": "natural_voice",
            "click_events_after": 8,
            "click_gate_pass": True,
            "echo_artifact_score": 0.31,
            "echo_gate_pass": True,
            "lufs_after": -14.1,
        },
        {
            "profile": "click_rescue",
            "click_events_after": 5,
            "click_gate_pass": True,
            "echo_artifact_score": 0.30,
            "echo_gate_pass": True,
            "lufs_after": -14.1,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=2, cfg=cfg)

    assert selected["profile"] == "natural_voice"


def test_echo_non_regression_blocks_more_echoey_candidate():
    cfg = AudioConfig(echo_artifact_max_score=0.42)
    candidates = [
        {
            "profile": "warm_room_tame",
            "click_events_after": 4,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.20,
            "echo_artifact_score": 0.30,
            "echo_gate_pass": False,
            "lufs_after": -14.0,
        },
        {
            "profile": "warm_click_tame",
            "click_events_after": 6,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.20,
            "echo_artifact_score": 0.19,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=20, cfg=cfg)

    assert selected["profile"] == "warm_click_tame"


def test_source_reference_wins_without_material_cleanup_improvement():
    cfg = AudioConfig(echo_artifact_max_score=0.42, require_heavy_backend=False)
    candidates = [
        {
            "profile": "source_reference",
            "click_events_after": 4,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.34,
            "echo_artifact_score": 0.34,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
        {
            "profile": "warm_deep_tame",
            "click_events_after": 8,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.34,
            "echo_artifact_score": 0.27,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=4, cfg=cfg)

    assert selected["profile"] == "source_reference"


def test_source_reference_cannot_satisfy_strong_cleanup_by_default():
    cfg = AudioConfig(echo_artifact_max_score=0.42)
    candidate = {
        "profile": "source_reference",
        "source_mode": "reference",
        "click_events_after": 0,
        "click_gate_pass": True,
        "echo_artifact_score": 0.2,
        "echo_gate_pass": True,
        "lufs_after": -14.0,
    }

    assert audio._strong_cleanup_gate_pass(candidate, cfg) is False


def test_high_echo_source_uses_source_relative_echo_gate():
    cfg = AudioConfig(echo_artifact_max_score=0.42)

    assert audio._echo_gate_pass(0.5797, 0.5792, cfg) is True
    assert audio._echo_gate_pass(0.5903, 0.5792, cfg) is False


def test_default_selector_prefers_passing_heavy_cleanup_over_source_reference():
    cfg = AudioConfig(echo_artifact_max_score=0.42)
    candidates = [
        {
            "profile": "source_reference",
            "source_mode": "reference",
            "wet_dry_mix": {"dry": 1.0, "wet": 0.0},
            "click_events_after": 0,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.18,
            "echo_artifact_score": 0.18,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
        {
            "profile": "natural_voice",
            "source_mode": "heavy",
            "wet_dry_mix": {"dry": 0.28, "wet": 0.72},
            "click_events_after": 2,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.18,
            "echo_artifact_score": 0.19,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=2, cfg=cfg)

    assert selected["profile"] == "natural_voice"
    assert audio._strong_cleanup_gate_pass(selected, cfg) is True


def test_heavy_required_selector_never_outputs_source_reference():
    cfg = AudioConfig(echo_artifact_max_score=0.42)
    candidates = [
        {
            "profile": "source_reference",
            "source_mode": "reference",
            "wet_dry_mix": {"dry": 1.0, "wet": 0.0},
            "click_events_after": 0,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.58,
            "echo_artifact_score": 0.58,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
        {
            "profile": "warm_model_10",
            "source_mode": "heavy",
            "wet_dry_mix": {"dry": 0.65, "wet": 0.35},
            "click_events_after": 0,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.58,
            "echo_artifact_score": 0.60,
            "echo_gate_pass": False,
            "lufs_after": -14.0,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=0, cfg=cfg)

    assert selected["profile"] == "warm_model_10"
    assert selected["source_mode"] == "heavy"


def test_source_reference_cannot_win_when_it_misses_loudness_target():
    cfg = AudioConfig(target_lufs=-14.0, echo_artifact_max_score=0.42)
    candidates = [
        {
            "profile": "source_reference",
            "click_events_after": 0,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.20,
            "echo_artifact_score": 0.20,
            "echo_gate_pass": True,
            "lufs_after": -23.7,
        },
        {
            "profile": "warm_click_tame",
            "click_events_after": 0,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.20,
            "echo_artifact_score": 0.21,
            "echo_gate_pass": True,
            "lufs_after": -14.5,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=0, cfg=cfg)

    assert selected["profile"] == "warm_click_tame"
    assert selected["loudness_gate_pass"] is True


def test_processed_candidate_can_beat_source_reference_with_big_click_reduction():
    cfg = AudioConfig(echo_artifact_max_score=0.42)
    candidates = [
        {
            "profile": "source_reference",
            "click_events_after": 40,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.22,
            "echo_artifact_score": 0.22,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
        {
            "profile": "click_rescue",
            "click_events_after": 9,
            "click_gate_pass": True,
            "reference_echo_artifact_score": 0.22,
            "echo_artifact_score": 0.225,
            "echo_gate_pass": True,
            "lufs_after": -14.0,
        },
    ]

    selected = audio._select_best_candidate(candidates, before_clicks=40, cfg=cfg)

    assert selected["profile"] == "click_rescue"


def test_heavy_enhancer_receipts_fall_back_without_false_claim(monkeypatch, tmp_path):
    raw = tmp_path / "raw.wav"
    raw.write_bytes(b"RIFF0000WAVE")
    cfg = AudioConfig(heavy_model_preference=["resemble-enhance", "deepfilternet"])
    monkeypatch.setattr(audio._backends.shutil, "which", lambda _name: None)
    monkeypatch.setattr(audio._backends, "_which_binary", lambda _name: None)
    monkeypatch.setattr(audio._backends, "find_resemble_enhance", lambda _env_dir: None)
    monkeypatch.setattr(audio._backends, "find_deep_filter", lambda _env_dir: None)

    src, backend, attempts = audio._heavy_enhance(raw, cfg, tmp_path)

    assert src == raw
    assert backend == "ffmpeg_only"
    assert attempts == [
        {"backend": "resemble-enhance", "available": False, "applied": False, "error": "not installed"},
        {"backend": "deepfilternet", "available": False, "applied": False, "error": "not installed"},
    ]


def test_studio_sound_requires_heavy_backend_by_default(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not-real-media")
    raw = tmp_path / "_audio" / "raw.wav"
    raw.parent.mkdir()
    raw.write_bytes(b"RIFF0000WAVE")

    monkeypatch.setattr(audio, "measure_lufs", lambda _media: -20.0)
    monkeypatch.setattr(audio, "run_ffmpeg", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(audio, "_click_event_count", lambda *_args, **_kwargs: 3)
    monkeypatch.setattr(
        audio,
        "_heavy_enhance",
        lambda in_wav, cfg, run_dir, receipts=None: (in_wav, "ffmpeg_only", [{"backend": "resemble-enhance", "available": False}]),
    )

    result = audio.studio_sound(video, tmp_path, AudioConfig(require_heavy_backend=True))

    assert result["applied"] is False
    assert result["quality_gate_pass"] is False
    assert result["enhancement_backend"] == "ffmpeg_only"
    assert "eddy studio-sound install" in result["error"]


def test_click_event_count_detects_impulse_clicks(tmp_path):
    import struct
    import wave

    wav = tmp_path / "click.wav"
    rate = 48000
    samples = [0] * rate
    samples[1000] = 32767
    samples[1001] = -32768
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    assert audio._click_event_count(wav, threshold=0.8) >= 1


def test_mouth_click_score_catches_smaller_transient_clicks(tmp_path):
    import struct
    import wave

    wav = tmp_path / "mouth-clicks.wav"
    rate = 48000
    samples = [0] * rate
    for offset in range(2000, 22000, 2000):
        samples[offset] = 14000
        samples[offset + 1] = -12000
        samples[offset + 2] = 0
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    assert audio._mouth_click_score(wav) > AudioConfig().mouth_click_score_max


def test_mouth_click_hotspot_finds_click_window(tmp_path):
    import struct
    import wave

    wav = tmp_path / "mouth-click-hotspot.wav"
    rate = 48000
    samples = [0] * (rate * 24)
    for offset in range(rate * 15, rate * 18, 4000):
        samples[offset] = 14000
        samples[offset + 1] = -12000
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    hotspot = audio._mouth_click_hotspot(wav, window_s=12.0)

    assert hotspot["measurable"] is True
    assert hotspot["start_s"] == 12.0
    assert hotspot["event_count"] > 0


def test_studio_sound_audition_matrix_writes_hook_and_worst_click_windows(monkeypatch, tmp_path):
    import struct
    import wave

    raw = tmp_path / "raw.wav"
    clean = tmp_path / "clean.wav"
    rate = 48000
    samples = [0] * rate
    with wave.open(str(raw), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    clean.write_bytes(raw.read_bytes())

    def fake_run_ffmpeg(argv, **kwargs):
        Path(argv[-1]).write_bytes(raw.read_bytes())

    monkeypatch.setattr(audio, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(audio, "_mouth_click_score", lambda *_args, **_kwargs: 0.0)
    selected = {
        "profile": "broadcast_clean",
        "path": str(clean),
        "source_mode": "heavy",
        "wet_dry_mix": {"wet": 0.8},
    }

    matrix = audio._write_audition_matrix(
        raw,
        clean,
        tmp_path / "samples",
        tmp_path,
        selected,
        [selected],
        AudioConfig(),
    )

    assert matrix["status"] == "pass"
    assert [window["id"] for window in matrix["windows"]] == ["hook", "worst_click"]
    assert Path(matrix["path"]).exists()
    assert matrix["candidate_rows"][0]["strong_cleanup_gate_pass"] is True


def test_resemble_enhance_uses_mps_on_apple_silicon(monkeypatch, tmp_path):
    raw = tmp_path / "raw.wav"
    raw.write_bytes(b"RIFF0000WAVE")
    out = tmp_path / "enhanced.wav"
    seen = {}

    monkeypatch.setattr(audio._backends, "find_resemble_enhance", lambda _env_dir: "/bin/resemble-enhance")
    monkeypatch.setattr(audio._backends.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(audio._backends.platform, "machine", lambda: "arm64")

    class Proc:
        returncode = 1

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

        def terminate(self):
            self.returncode = -15

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        return Proc()

    monkeypatch.setattr(audio._backends.subprocess, "Popen", fake_popen)

    assert audio._resemble_enhance(raw, out, AudioConfig(heavy_model_device="auto"), tmp_path) is False
    assert "--device" in seen["cmd"]
    assert "mps" in seen["cmd"]


def test_spectral_repair_chain_uses_strong_click_cleanup(monkeypatch):
    monkeypatch.setattr(
        audio._filters,
        "_available_audio_filters",
        lambda: frozenset({"adeclick", "aclick", "adeclip", "deesser", "afade"}),
    )
    chain = audio._spectral_repair_chain(AudioConfig())
    assert chain.count("adeclick") >= 2
    assert "deesser" in chain
