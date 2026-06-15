"""v0.5: live progress + ETA so a multi-minute run never looks frozen."""

from eddy.loop.controller import _fmt_dur, _loop_progress


def test_fmt_dur():
    assert _fmt_dur(5) == "5s"
    assert _fmt_dur(65) == "1m05s"
    assert _fmt_dur(0) == "0s"
    assert _fmt_dur(-3) == "0s"  # clamped


def test_loop_progress_over_ceiling_with_eta():
    s = _loop_progress(2, 15, 7.5, 8.2, 120.0, 60.0)
    assert "cut 2/15" in s
    assert "q7.50" in s and "judge8.2" in s
    assert "2m00s over ceiling" in s
    assert "left" in s  # 13 iterations remain -> an ETA is shown


def test_loop_progress_last_iter_under_ceiling_no_eta():
    s = _loop_progress(15, 15, 9.0, 9.0, 0.0, 100.0)
    assert "under ceiling" in s
    assert "left" not in s  # no remaining iterations -> no ETA
