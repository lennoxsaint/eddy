from __future__ import annotations

import json
from pathlib import Path

from eddy.config import EddyConfig
from eddy.host_agent import host_packet, submit_host_decisions


def _run_dir(tmp_path):
    rd = tmp_path / "run"
    (rd / "transcript").mkdir(parents=True)
    source = tmp_path / "camera.mp4"
    screen = tmp_path / "screen.mp4"
    source.write_bytes(b"fake")
    screen.write_bytes(b"screen")
    (rd / "manifest.json").write_text(
        json.dumps(
            {
                "sources": {"camera": str(source), "screen": str(screen)},
                "source_sha256": {"camera": "abc", "screen": "def"},
            }
        )
    )
    (rd / "transcript" / "takes_packed.md").write_text("[0.10-1.20] hello useful world\n[2.00-3.10] hello useful world\n")
    (rd / "transcript" / "words.json").write_text(
        json.dumps(
            {
                "source_sha256": "abc",
                "segments": [
                    {
                        "words": [
                            {"start": 0.1, "end": 0.4, "word": "hello", "probability": 0.99},
                            {"start": 0.5, "end": 0.8, "word": " useful", "probability": 0.99},
                            {"start": 0.9, "end": 1.2, "word": " world", "probability": 0.99},
                            {"start": 2.0, "end": 2.3, "word": " hello", "probability": 0.99},
                            {"start": 2.4, "end": 2.7, "word": " useful", "probability": 0.99},
                            {"start": 2.8, "end": 3.1, "word": " world", "probability": 0.99},
                        ]
                    }
                ],
            }
        )
    )
    (rd / "transcript" / "phrases.json").write_text(
        json.dumps([
            {"start": 0.1, "end": 1.2, "text": "hello useful world"},
            {"start": 2.0, "end": 3.1, "text": "hello useful world"},
        ])
    )
    (rd / "transcript" / "silence-map.json").write_text(
        json.dumps([{"after_s": 1.2, "gap_s": 0.8, "before_word": "world", "next_word": "hello"}])
    )
    (rd / "transcript" / "audio-silence.json").write_text("[]")
    return rd


def test_host_packet_includes_context_but_never_media_bytes(tmp_path):
    rd = _run_dir(tmp_path)
    packet = host_packet(rd)
    assert packet["status"] == "ready"
    assert packet["contract"] == "host_intent_v1"
    assert "hello useful world" in packet["transcript"]["excerpt"]
    assert packet["sources"]["camera"]["bytes_included"] is False
    assert packet["sources"]["screen"]["bytes_included"] is False
    assert packet["media_policy"] == "No media bytes are included in this packet."
    assert packet["candidate_context"]["count"] >= 1
    assert packet["candidate_context"]["candidates"][0]["id"]
    assert packet["candidate_context"]["candidates"][0]["reason"]


def test_host_submit_compiles_valid_decisions(monkeypatch, tmp_path):
    rd = _run_dir(tmp_path)
    monkeypatch.setattr("eddy.host_agent.duration_s", lambda path: 2.0)
    monkeypatch.setattr("eddy.host_agent.load_config", lambda: EddyConfig())

    out = submit_host_decisions(rd, {"target_runtime_seconds": 2.0, "cuts": []})
    assert out["status"] == "compiled"
    assert out["ranges"] == 1
    assert out["contract"] == "EditDecisions"
    assert (rd / "host-agent").exists()
    assert (rd / "iterations" / "01" / "edit-decisions.json").exists()
    assert (rd / "iterations" / "01" / "edl.json").exists()
    edl = json.loads((rd / "iterations" / "01" / "edl.json").read_text())
    sim = json.loads((rd / "iterations" / "01" / "sim-report.json").read_text())
    assert edl["sources"]["screen"].endswith("screen.mp4")
    assert "boundary_cards" in sim
    assert "verdicts" in sim
    assert "pass" in sim
    assert tuple(Path(out["iteration_dir"]).parts[-2:]) == ("iterations", "01")


def test_host_submit_invalid_payload_returns_blocker(tmp_path):
    rd = _run_dir(tmp_path)
    out = submit_host_decisions(rd, {"cuts": [{"start_s": "not-a-number", "end_s": 1.0}]})
    assert out["status"] == "blocked"
    assert out["blockers"][0]["code"] == "invalid_host_payload"


def test_host_intent_selected_candidate_compiles(monkeypatch, tmp_path):
    rd = _run_dir(tmp_path)
    monkeypatch.setattr("eddy.host_agent.duration_s", lambda path: 4.0)
    monkeypatch.setattr("eddy.host_agent.load_config", lambda: EddyConfig())
    packet = host_packet(rd)
    candidate_id = next(c["id"] for c in packet["candidate_context"]["candidates"] if c["kind"] == "retake")

    out = submit_host_decisions(
        rd,
        {
            "contract": "host_intent_v1",
            "edit_goal": "make this clear and concise",
            "keep_priorities": ["keep the final clean take"],
            "drop_priorities": ["drop earlier repeated takes"],
            "retake_policy": "last_take_bias",
            "gap_policy": "natural_micro_pauses",
            "pacing_preference": "medium_clarity",
            "selected_candidate_ids": [candidate_id],
            "candidate_annotations": {candidate_id: "Earlier take before the cleaner repeat."},
        },
    )

    assert out["status"] == "compiled"
    assert out["contract"] == "host_intent_v1"
    decisions = json.loads((rd / "iterations" / "01" / "edit-decisions.json").read_text())
    assert decisions["retakes"][0]["kept_take"] == "last"
    assert decisions["x_eddy"]["directive"][0]["selected_candidate_ids"] == [candidate_id]
    assert (rd / "host-agent" / "repair-history.json").exists()


def test_host_intent_rejects_unknown_candidate_id(tmp_path):
    rd = _run_dir(tmp_path)
    out = submit_host_decisions(rd, {"contract": "host_intent_v1", "selected_candidate_ids": ["missing_001"]})
    assert out["status"] == "blocked"
    assert out["blockers"][0]["code"] == "unknown_host_candidate_ids"


def test_host_intent_rejects_raw_timestamps_without_expert_override(tmp_path):
    rd = _run_dir(tmp_path)
    out = submit_host_decisions(
        rd,
        {
            "contract": "host_intent_v1",
            "raw_cuts": [{"start_s": 0.1, "end_s": 1.0, "reason": "freehand cut"}],
        },
    )
    assert out["status"] == "blocked"
    assert out["blockers"][0]["code"] == "raw_timestamp_override_requires_expert_override"
