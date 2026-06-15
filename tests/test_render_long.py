"""v1.0: small pure-logic coverage for the long-render iteration resolver."""

import pytest

from eddy.render.long import latest_iteration_dir


def test_latest_iteration_dir_picks_highest(tmp_path):
    for n in ("01", "02", "10"):
        (tmp_path / "iterations" / n).mkdir(parents=True)
    assert latest_iteration_dir(tmp_path).name == "10"  # numeric-padded sort, highest last


def test_latest_iteration_dir_raises_when_none(tmp_path):
    (tmp_path / "iterations").mkdir()
    with pytest.raises(FileNotFoundError, match="run `eddy plan` first"):
        latest_iteration_dir(tmp_path)
