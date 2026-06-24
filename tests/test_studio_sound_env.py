from pathlib import Path

from eddy import studio_sound_env as env


def test_studio_sound_status_is_notify_only(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "find_backend_python", lambda: "/usr/bin/python3.11")
    monkeypatch.setattr(env, "find_deep_filter", lambda _env_dir=env.DEFAULT_ENV: None)
    monkeypatch.setattr(env, "find_resemble_enhance", lambda _env_dir=env.DEFAULT_ENV: None)
    monkeypatch.setattr(env, "_module_available", lambda _name: False)
    monkeypatch.setattr(env, "_module_available_in_env", lambda _env_dir, _name: False)

    res = env.status(tmp_path / "studio")

    assert res["quality_ready"] is False
    assert res["default_backend"] == "deepfilternet"
    assert res["install_command"] == "eddy studio-sound install"


def test_find_resemble_enhance_prefers_local_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "resemble-enhance"
    binary.write_text("#!/bin/sh\n")

    assert env.find_resemble_enhance(tmp_path) == str(binary)


def test_status_requires_deepfilter_not_git_lfs(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "find_backend_python", lambda: "/usr/bin/python3.11")
    monkeypatch.setattr(env, "find_deep_filter", lambda _env_dir=env.DEFAULT_ENV: "/tmp/deepFilter")
    monkeypatch.setattr(env, "find_resemble_enhance", lambda _env_dir=env.DEFAULT_ENV: "/tmp/resemble-enhance")
    monkeypatch.setattr(env, "_module_available", lambda name: name in {"torch", "torchaudio", "soundfile"})
    monkeypatch.setattr(env, "_module_available_in_env", lambda _env_dir, name: name in {"torch", "torchaudio", "soundfile"})
    monkeypatch.setattr(env.shutil, "which", lambda _name: None)

    res = env.status(tmp_path / "studio")

    assert res["quality_ready"] is True
    assert res["git_lfs"] is None


def test_install_deepfilternet_reports_missing_rust(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda _name: None)

    res = env.install_deepfilternet()

    assert res["ok"] is False
    assert res["stage"] == "rust"
    assert "Rust" in res["error"]


def test_install_studio_sound_installs_default_backend(monkeypatch):
    class Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    calls = []
    monkeypatch.setattr(env.shutil, "which", lambda name: "/usr/bin/cargo" if name == "cargo" else None)
    monkeypatch.setattr(env, "find_backend_python", lambda: "/usr/bin/python3.11")
    monkeypatch.setattr(env, "env_python", lambda _env_dir=env.DEFAULT_ENV: Path("/tmp/studio/bin/python"))
    monkeypatch.setattr(env.subprocess, "run", lambda cmd, **_kwargs: calls.append(cmd) or Proc())
    monkeypatch.setattr(env, "status", lambda env_dir=env.DEFAULT_ENV: {"quality_ready": True, "deep_filter": "/tmp/deepFilter"})

    res = env.install_studio_sound()

    assert res["ok"] is True
    assert any("deepfilternet" in item for cmd in calls for item in cmd)
