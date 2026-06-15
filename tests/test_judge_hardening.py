"""v0.4: the judge boundary is adversarial. A local q4 model can return out-of-range scores,
missing dimensions, or malformed defects. None may crash the run or sail past the 8.0 ship gate.
"""

from eddy.edit.schema import Edl, EditDecisions
from eddy.qa.judge import _consistent, run_judge, weighted_score


class _Receipts:
    def log(self, *a, **k):
        pass


class _Stub:
    name = "stub"

    def __init__(self, payload):
        self.payload = payload

    def complete(self, *a, **k):
        return self.payload


SIM = {"duration_s": 600, "target_s": 600, "ranges": 1, "removed_total_s": 0, "boundary_cards": []}
_DIMS = ("hook_integrity", "boundary_continuity", "pacing", "completeness", "ending_cta")


def _run(payload):
    return run_judge(_Stub(payload), _Receipts(), SIM, EditDecisions(), Edl(sources={}, ranges=[]), [], None)


def test_weighted_score_clamps_out_of_range():
    assert weighted_score({k: 50 for k in _DIMS}) == 10.0   # not 50
    assert weighted_score({k: 0 for k in _DIMS}) == 1.0      # not 0
    assert weighted_score({k: -5 for k in _DIMS}) == 1.0


def test_weighted_score_missing_dimension_defaults_worst_not_crash():
    s = weighted_score({"hook_integrity": 10})  # other 4 missing
    # hook 10*2 + four missing->1 each: (20 + 1*3 + 1*3 + 1*2 + 1*1)/11
    assert s == round((20 + 3 + 3 + 2 + 1) / 11, 2)


def test_weighted_score_non_dict_is_zero():
    assert weighted_score("garbage") == 0.0
    assert weighted_score(None) == 0.0


def test_consistent_tolerates_defect_without_severity():
    # must not KeyError on a malformed defect
    assert _consistent({"scores": {k: 9 for k in _DIMS}, "defects": [{"type": "drag"}]}) in (True, False)


def test_run_judge_clamps_inflated_score():
    r = _run({"scores": {k: 50 for k in _DIMS}, "defects": [], "summary": "ok"})
    assert r["weighted"] == 10.0  # clamped — a 50 cannot inflate past the gate


def test_run_judge_survives_malformed_payload_no_crash():
    r = _run({"scores": {"hook_integrity": 9}, "defects": [{"type": "drag"}], "summary": "x"})
    assert r["weighted"] == round((18 + 3 + 3 + 2 + 1) / 11, 2)
    assert "judge_unstable" in r


def test_run_judge_non_dict_payload_degrades_to_unstable():
    r = _run(["not", "an", "object"])
    assert r["judge_unstable"] is True
    assert r["weighted"] == 0.0
