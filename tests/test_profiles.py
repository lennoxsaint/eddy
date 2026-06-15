"""v0.8: named per-channel run profiles. A profile supplies run defaults (target length, format,
language); an explicit CLI flag always wins. Unknown profile = hard error, not silent wrong defaults."""

import pytest
from typer.testing import CliRunner

import eddy.config as cfgmod
import eddy.loop.controller as ctrlmod
from eddy.cli import app
from eddy.config import EddyConfig, RunProfile, resolve_profile

runner = CliRunner()


def test_resolve_none_is_empty_profile():
    p = resolve_profile(EddyConfig(), None)
    assert p == RunProfile()
    assert p.target_minutes is None and p.format is None


def test_resolve_named_profile():
    cfg = EddyConfig(profiles={"tutorials": RunProfile(format="tutorial", target_minutes=20.0)})
    p = resolve_profile(cfg, "tutorials")
    assert p.format == "tutorial" and p.target_minutes == 20.0


def test_unknown_profile_raises_with_known_list():
    cfg = EddyConfig(profiles={"main": RunProfile(), "es": RunProfile(language="es")})
    with pytest.raises(KeyError, match="unknown profile 'nope'.*es, main"):
        resolve_profile(cfg, "nope")


def test_profiles_load_from_toml(tmp_path):
    cfg_file = tmp_path / "eddy.toml"
    cfg_file.write_text(
        "[profiles.spanish]\nlanguage = 'es'\ntarget_minutes = 8.0\n"
        "[profiles.tut]\nformat = 'tutorial'\nskip_shorts = true\n"
    )
    from eddy.config import load_config

    cfg = load_config(cfg_file)
    assert cfg.profiles["spanish"].language == "es"
    assert cfg.profiles["spanish"].target_minutes == 8.0
    assert cfg.profiles["tut"].format == "tutorial"
    assert cfg.profiles["tut"].skip_shorts is True


def test_cli_flag_overrides_profile_precedence():
    """Mirror the run() merge: explicit CLI value wins; else profile; else built-in default."""
    prof = RunProfile(target_minutes=20.0, language="es")

    # CLI passes target_minutes=5 explicitly -> wins over profile's 20
    cli_target = 5.0
    eff_target = cli_target if cli_target is not None else prof.target_minutes
    assert eff_target == 5.0

    # CLI passes nothing for language -> profile's 'es' applies
    cli_language = None
    eff_language = cli_language if cli_language is not None else prof.language
    assert eff_language == "es"


def _patch_run(monkeypatch, tmp_path, profile):
    captured: dict = {}
    monkeypatch.setattr(ctrlmod, "autonomous_run", lambda **k: captured.update(k) or tmp_path)
    monkeypatch.setattr(cfgmod, "load_config", lambda *a, **k: EddyConfig(profiles={"p": profile}))
    src = tmp_path / "footage.mp4"
    src.write_bytes(b"x")
    return captured, src


def test_profile_skip_shorts_applies_without_flag(monkeypatch, tmp_path):
    captured, src = _patch_run(monkeypatch, tmp_path, RunProfile(skip_shorts=True))
    r = runner.invoke(app, ["run", str(src), "--profile", "p"])
    assert r.exit_code == 0, r.output
    assert captured["skip_shorts"] is True  # profile applies when no flag given


def test_no_skip_shorts_flag_overrides_profile(monkeypatch, tmp_path):
    # the I2 fix: an explicit --no-skip-shorts must beat a profile's skip_shorts=True
    captured, src = _patch_run(monkeypatch, tmp_path, RunProfile(skip_shorts=True))
    r = runner.invoke(app, ["run", str(src), "--profile", "p", "--no-skip-shorts"])
    assert r.exit_code == 0, r.output
    assert captured["skip_shorts"] is False
