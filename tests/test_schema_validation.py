"""v0.4: validate_against recursively checks nested required keys, types, and enums at the
provider boundary, so structurally-wrong model output retries instead of crashing/false-passing.
"""

import pytest

from eddy.edit.cutplan import DECISIONS_SCHEMA
from eddy.providers.base import ProviderError, validate_against
from eddy.qa.judge import JUDGE_SCHEMA

NUM = {"type": "object", "required": ["x"], "properties": {"x": {"type": "number"}}}
_DIMS = ("hook_integrity", "boundary_continuity", "pacing", "completeness", "ending_cta")


def _valid_decisions():
    return {
        "retakes": [],
        "cuts": [{"start_s": 1.0, "end_s": 2.0, "tier": "MANDATORY"}],
        "protected_moments": [],
        "shorts_candidates": [],
    }


def _valid_judge():
    return {"defects": [{"out_s": 1, "quote": "q", "type": "drag", "severity": "major", "fix_op": "drop_beat"}],
            "scores": {k: 8 for k in _DIMS}, "summary": "x"}


def test_valid_decisions_pass_through():
    d = _valid_decisions()
    assert validate_against(DECISIONS_SCHEMA, d) is d


def test_top_level_missing_required_still_raises():
    bad = _valid_decisions()
    del bad["cuts"]
    with pytest.raises(ProviderError, match="cuts"):
        validate_against(DECISIONS_SCHEMA, bad)


def test_nested_missing_required_raises():
    bad = _valid_decisions()
    del bad["cuts"][0]["tier"]  # nested required — old top-level-only check missed this
    with pytest.raises(ProviderError, match="tier"):
        validate_against(DECISIONS_SCHEMA, bad)


def test_wrong_enum_raises():
    bad = _valid_decisions()
    bad["cuts"][0]["tier"] = "HUGE"
    with pytest.raises(ProviderError):
        validate_against(DECISIONS_SCHEMA, bad)


def test_wrong_container_type_raises():
    bad = _valid_decisions()
    bad["cuts"] = {"start_s": 1}  # object where array required
    with pytest.raises(ProviderError, match="expected array"):
        validate_against(DECISIONS_SCHEMA, bad)


def test_judge_missing_score_dimension_raises():
    bad = _valid_judge()
    del bad["scores"]["pacing"]
    with pytest.raises(ProviderError, match="pacing"):
        validate_against(JUDGE_SCHEMA, bad)


def test_judge_defect_missing_severity_raises():
    bad = _valid_judge()
    del bad["defects"][0]["severity"]
    with pytest.raises(ProviderError, match="severity"):
        validate_against(JUDGE_SCHEMA, bad)


def test_number_field_rejects_list_and_bool_but_accepts_numeric_string():
    with pytest.raises(ProviderError, match="expected number"):
        validate_against(NUM, {"x": [1]})
    with pytest.raises(ProviderError, match="expected number"):
        validate_against(NUM, {"x": True})  # JSON bool must not satisfy a number
    assert validate_against(NUM, {"x": "12.5"}) == {"x": "12.5"}  # pydantic coerces later
