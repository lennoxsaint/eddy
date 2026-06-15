"""v0.6: config schema migration + a tolerant loader (a malformed/old config must not brick every
command) + the runs_dir case-collision fix."""

from eddy.config import EddyConfig, load_config, migrate_config


def test_migrate_stamps_schema_version():
    assert migrate_config({})["schema_version"] == 1
    assert migrate_config({"schema_version": 1, "provider": {}})["schema_version"] == 1


def test_runs_dir_is_lowercase_hidden_no_collision():
    s = str(EddyConfig().runs_dir)
    assert ".eddy" in s and s.endswith("runs")  # ~/.eddy/runs, not ~/Eddy/runs


def test_load_config_missing_file_is_defaults(tmp_path):
    assert isinstance(load_config(tmp_path / "nope.toml"), EddyConfig)


def test_load_config_valid_roundtrip_and_stamps_version(tmp_path):
    good = tmp_path / "eddy.toml"
    good.write_text('[provider]\nactive = "ollama"\n[loop]\nmax_iterations = 7\n')
    cfg = load_config(good)
    assert cfg.provider.active == "ollama" and cfg.loop.max_iterations == 7
    assert cfg.schema_version == 1  # migrate_config stamped it


def test_load_config_tolerates_malformed_does_not_crash(tmp_path, capsys):
    bad = tmp_path / "eddy.toml"
    bad.write_text('[loop]\nmax_iterations = "not a number"\n')
    cfg = load_config(bad)
    assert isinstance(cfg, EddyConfig)  # defaults, not a ValidationError that bricks every command
    assert cfg.loop.max_iterations == 15  # default
    assert "could not load config" in capsys.readouterr().err
