from __future__ import annotations

import json
from pathlib import Path

import pytest

from eddy.feedback import record_owner_feedback


def valid_feedback() -> dict:
    return {
        "schema_version": "owner-feedback-v1",
        "job_id": "job-1",
        "verdict": "approved_after_repair",
        "approval_scope": ["all_three_longs", "all_three_shorts"],
        "summary": "Best run so far after terminal punctuation repair.",
        "issues": [
            {
                "artifact": "shorts/*",
                "evidence": "Sentence-ending periods were stripped from burned captions.",
                "category": "deterministic_bug",
                "scope": "future_edits",
                "desired_correction": "Preserve terminal periods, questions, and exclamations.",
            }
        ],
    }


def test_owner_feedback_is_typed_and_written_beside_the_run(tmp_path: Path) -> None:
    result = record_owner_feedback(tmp_path, "job-1", valid_feedback())

    assert result["status"] == "recorded"
    written = json.loads((tmp_path / "review" / "owner-feedback.json").read_text())
    assert written["issues"][0]["category"] == "deterministic_bug"
    assert written["issues"][0]["scope"] == "future_edits"


def test_owner_feedback_rejects_unknown_learning_categories(tmp_path: Path) -> None:
    payload = valid_feedback()
    payload["issues"][0]["category"] = "make_it_magic"

    with pytest.raises(ValueError, match="owner_feedback_issue_category_invalid"):
        record_owner_feedback(tmp_path, "job-1", payload)
