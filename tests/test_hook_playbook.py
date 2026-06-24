import json
import subprocess
from pathlib import Path

import pytest

from eddy.hooks.playbook import (
    build_from_youtube_metadata,
    dedupe_records,
    playbook_status,
    score_candidate_hook,
    require_hook_playbook,
    validate_hook_record,
)


def _record(i: int) -> dict:
    return {
        "hook_id": f"h{i}",
        "source_url": f"https://example.com/short/{i}",
        "platform": "youtube",
        "source_type": "short_form_metadata",
        "opening_3s_text": f"This is the opening hook number {i}",
        "first_3_second_rationale": "Synthetic test hook with explicit opening rationale.",
        "hook_pattern": "curiosity with proof",
        "pattern_tags": ["curiosity", "proof"],
        "payoff_type": "closed loop",
        "proven_score": 0.82,
        "score_signals": {"test": True},
        "provenance": {"source": "test"},
    }


def test_validate_hook_record_requires_public_proven_hook():
    ok, problems = validate_hook_record(_record(1))
    assert ok
    assert problems == []

    ok, problems = validate_hook_record({"source_url": "local"})
    assert not ok
    assert "source_url_not_public" in problems


def test_hook_playbook_blocks_below_1000(tmp_path):
    path = tmp_path / "hooks.jsonl"
    path.write_text(json.dumps(_record(1)) + "\n")

    status = playbook_status(path, min_records=1000)

    assert status["ready"] is False
    assert status["blocker"] == "short_form_hook_playbook_below_1000_valid_hooks"
    with pytest.raises(RuntimeError, match="below_1000"):
        require_hook_playbook(path, min_records=1000)


def test_hook_playbook_ready_at_threshold(tmp_path):
    path = tmp_path / "hooks.jsonl"
    path.write_text("\n".join(json.dumps(_record(i)) for i in range(3)) + "\n")

    assert playbook_status(path, min_records=3)["ready"] is True


def test_dedupe_records_removes_duplicate_openings_and_sources():
    a = _record(1)
    b = {**_record(2), "opening_3s_text": a["opening_3s_text"]}
    c = {**_record(3), "source_url": a["source_url"]}

    assert len(dedupe_records([a, b, c])) == 1


def test_build_from_youtube_metadata_records_title_surrogate_hooks(tmp_path, monkeypatch):
    payload = {
        "id": "abc123",
        "webpage_url": "https://www.youtube.com/watch?v=abc123",
        "title": "Stop making this creator mistake #shorts",
        "duration": 31,
        "channel": "Example Creator",
        "view_count": 100000,
    }

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(_args[0], 0, stdout=json.dumps(payload) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = tmp_path / "hooks.jsonl"

    status = build_from_youtube_metadata(out, queries=["#shorts creator mistakes"], target_records=1, min_records=1)
    rec = json.loads(out.read_text().splitlines()[0])

    assert status["ready"] is True
    assert rec["provenance"]["source"] == "yt-dlp-youtube-metadata"
    assert rec["provenance"]["title_as_opening_surrogate"] is True
    assert rec["hook_pattern"] == "mistake warning"


def test_candidate_hook_scoring_uses_playbook_patterns():
    records = [
        {
            **_record(1),
            "opening_3s_text": "Stop making this creator mistake",
            "hook_pattern": "mistake warning",
        }
    ]

    strong = score_candidate_hook("Stop making this creator mistake today", records)
    weak = score_candidate_hook("and then I went over here", records)

    assert strong["pass"] is True
    assert strong["hook_score"] > weak["hook_score"]
    assert weak["pass"] is False


def test_baked_hook_playbook_is_runtime_ready():
    path = Path(__file__).resolve().parents[1] / "docs" / "references" / "short-form-hook-playbook.jsonl"

    status = playbook_status(path, min_records=1000)

    assert status["ready"] is True
    assert status["valid_count"] >= 1000
    assert status["invalid_count"] == 0
    assert "yt-dlp-youtube-metadata" in status["provenance_sources"]
