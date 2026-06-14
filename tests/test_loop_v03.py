"""v0.3 loop: best() ranking on gate-fail, gate-pass maximizes quality, judge no-auto-pass."""

from eddy.loop.state import RunState
from eddy.providers.base import ProviderError
from eddy.qa.judge import run_judge


class _Receipts:
    def log(self, *a, **k):
        pass


def test_gatefail_ranking_prefers_closer_to_feasible(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    # both fail gates: iter1 high quality but far over ceiling; iter2 lower quality but near it
    s.record_attempt(1, False, 9.0, 100, quality=8.0, over_ceiling_s=600)
    s.record_attempt(2, False, 5.0, 50, quality=4.0, over_ceiling_s=60)
    assert s.best()["iteration"] == 2  # closer-to-feasible wins, not the longest/highest-judge


def test_gatepass_ranking_maximizes_quality(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.record_attempt(1, True, 7.0, 10, quality=6.0, over_ceiling_s=0)
    s.record_attempt(2, True, 7.0, 10, quality=8.5, over_ceiling_s=0)
    assert s.best()["iteration"] == 2


def test_gatepass_outranks_higher_quality_gatefail(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.record_attempt(1, False, 9.0, 0, quality=9.5, over_ceiling_s=0)
    s.record_attempt(2, True, 5.0, 0, quality=5.0, over_ceiling_s=0)
    assert s.best()["iteration"] == 2  # a passing edit always beats a failing one


def test_plateau_state_persists(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.set_plateau(2, 7.3)
    assert RunState(tmp_path / "r").data["no_improve"] == 2
    assert RunState(tmp_path / "r").data["prev_best_q"] == 7.3


def test_run_judge_unavailable_does_not_auto_pass(tmp_path):
    class Dead:
        name = "dead"

        def complete(self, *a, **k):
            raise ProviderError("provider down")

    sim = {
        "duration_s": 600, "target_s": 600, "ranges": 1, "removed_total_s": 0,
        "boundary_cards": [],
    }

    class _D:
        class x_eddy:
            beats = []

    res = run_judge(Dead(), _Receipts(), sim, _D(), None, [], None)
    assert res["judge_unstable"] is True
    assert res["weighted"] == 0.0
    assert "advisory_only" not in res  # the auto-pass key is gone
