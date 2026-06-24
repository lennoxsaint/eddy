from eddy.config import AudioConfig
from eddy.render import audio


def test_speech_eq_includes_local_studio_sound_cleanup_when_filters_exist(monkeypatch):
    monkeypatch.setattr(
        audio,
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
    monkeypatch.setattr(audio, "_available_audio_filters", lambda: frozenset())
    chain = audio._speech_eq(AudioConfig())
    assert "highpass" in chain
    assert "equalizer" in chain
    assert "alimiter" in chain
    assert "adeclick" not in chain


def test_auto_profile_names_resolve_to_known_candidates():
    cfg = AudioConfig(studio_sound_profile="auto")

    assert audio._studio_sound_profile_names(cfg) == [
        "warm_room_tame",
        "warm_deep_tame",
        "warm_click_tame",
        "warm_model_10",
        "natural_voice",
        "click_rescue",
    ]


def test_warm_room_tame_profile_is_source_first_and_warm(monkeypatch):
    monkeypatch.setattr(
        audio,
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


def test_natural_profile_avoids_echo_prone_filters(monkeypatch):
    monkeypatch.setattr(
        audio,
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


def test_heavy_enhancer_receipts_fall_back_without_false_claim(monkeypatch, tmp_path):
    raw = tmp_path / "raw.wav"
    raw.write_bytes(b"RIFF0000WAVE")
    cfg = AudioConfig(heavy_model_preference=["resemble-enhance", "deepfilternet"])
    monkeypatch.setattr(audio.shutil, "which", lambda _name: None)
    monkeypatch.setattr(audio, "_which_binary", lambda _name: None)
    monkeypatch.setattr(audio, "find_resemble_enhance", lambda _env_dir: None)
    monkeypatch.setattr(audio, "find_deep_filter", lambda _env_dir: None)

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


def test_resemble_enhance_uses_mps_on_apple_silicon(monkeypatch, tmp_path):
    raw = tmp_path / "raw.wav"
    raw.write_bytes(b"RIFF0000WAVE")
    out = tmp_path / "enhanced.wav"
    seen = {}

    monkeypatch.setattr(audio, "find_resemble_enhance", lambda _env_dir: "/bin/resemble-enhance")
    monkeypatch.setattr(audio.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(audio.platform, "machine", lambda: "arm64")

    class Proc:
        returncode = 1
        stdout = ""
        stderr = "no output"

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return Proc()

    monkeypatch.setattr(audio.subprocess, "run", fake_run)

    assert audio._resemble_enhance(raw, out, AudioConfig(heavy_model_device="auto"), tmp_path) is False
    assert "--device" in seen["cmd"]
    assert "mps" in seen["cmd"]


def test_spectral_repair_chain_uses_strong_click_cleanup(monkeypatch):
    monkeypatch.setattr(
        audio,
        "_available_audio_filters",
        lambda: frozenset({"adeclick", "aclick", "adeclip", "deesser", "afade"}),
    )
    chain = audio._spectral_repair_chain(AudioConfig())
    assert chain.count("adeclick") >= 2
    assert "deesser" in chain
