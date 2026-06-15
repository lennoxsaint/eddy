"""v0.7: creator-facing review notes — plain-language 'review these moments' for a non-engineer."""

import json

from eddy.package.review import _ts, build_review, format_review


def test_ts():
    assert _ts(0) == "00:00"
    assert _ts(154) == "02:34"


def test_format_review_lists_flagged_moments():
    defects = [
        {"out_s": 154, "type": "bad_splice", "quote": "and so the thing", "severity": "major"},
        {"out_s": 30, "type": "drag", "severity": "minor"},
    ]
    md = format_review(defects, duration_s=600, ceiling_s=840, qa_pass=False, shipped_with_failures=True)
    assert "2 moment(s) Eddy was unsure about" in md
    assert "[02:34]" in md and "bad splice" in md
    assert "strongest attempt" in md and "CHECK" in md


def test_format_review_clean_cut():
    md = format_review([], duration_s=600, ceiling_s=840, qa_pass=True, shipped_with_failures=False)
    assert "clean first cut" in md and "PASS" in md
    assert "unsure about" not in md


def test_format_review_over_ceiling_length_note():
    md = format_review([], duration_s=2100, ceiling_s=840, qa_pass=True, shipped_with_failures=False)
    assert "Length: 35:00" in md and "over the target" in md


def test_build_review_writes_file_and_reads_judge(tmp_path):
    (tmp_path / "final").mkdir(parents=True)
    (tmp_path / "final" / "qa-final.json").write_text(json.dumps({"pass": True}))
    it = tmp_path / "iterations" / "01"
    it.mkdir(parents=True)
    (it / "judge.json").write_text(json.dumps({"defects": [{"out_s": 10, "type": "drag", "severity": "minor"}]}))
    info = build_review(tmp_path, it, duration_s=600, ceiling_s=840)
    review_md = (tmp_path / "final" / "REVIEW.md")
    assert review_md.exists() and info["flagged"] == 1
    assert "drag" in review_md.read_text()
    assert info["shipped_with_failures"] is True  # a defect present despite qa pass
