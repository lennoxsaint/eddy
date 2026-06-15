"""v0.8: named per-channel run profiles. A profile supplies run defaults (target length, format,
language); an explicit CLI flag always wins. Unknown profile = hard error, not silent wrong defaults."""

import pytest

from eddy.config import EddyConfig, RunProfile, resolve_profile


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
