from __future__ import annotations

import json
from pathlib import Path

from eddy.config import EddyConfig
from eddy.host_agent import host_packet, submit_host_decisions


def _run_dir(tmp_path):
    rd = tmp_path / "run"
    (rd / "transcript").mkdir(parents=True)
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"fake")
    (rd / "manifest.json").write_text(
        json.dumps({"sources": {"camera": str(source)}, "source_sha256": {"camera": "abc"}})
    )
    (rd / "transcript" / "takes_packed.md").write_text("[0.00-2.00] hello world")
    (rd / "transcript" / "words.json").write_text(
        json.dumps(
            {
                "source_sha256": "abc",
                "segments": [
                    {
                        "words": [
                            {"start": 0.1, "end": 0.5, "word": "hello", "probability": 0.99},
                            {"start": 0.6, "end": 1.1, "word": "world", "probability": 0.99},
                        ]
                    }
                ],
            }
        )
    )
    (rd / "transcript" / "phrases.json").write_text(json.dumps([{"start": 0.1, "end": 1.1, "text": "hello world"}]))
    (rd / "transcript" / "audio-silence.json").write_text("[]")
    return rd


def test_host_packet_includes_context_but_never_media_bytes(tmp_path):
    rd = _run_dir(tmp_path)
    packet = host_packet(rd)
    assert packet["status"] == "ready"
    assert "hello world" in packet["transcript"]["excerpt"]
    assert packet["sources"]["camera"]["bytes_included"] is False
    assert packet["media_policy"] == "No media bytes are included in this packet."


def test_host_submit_compiles_valid_decisions(monkeypatch, tmp_path):
    rd = _run_dir(tmp_path)
    monkeypatch.setattr("eddy.host_agent.duration_s", lambda path: 2.0)
    monkeypatch.setattr("eddy.host_agent.load_config", lambda: EddyConfig())

    out = submit_host_decisions(rd, {"target_runtime_seconds": 2.0, "cuts": []})
    assert out["status"] == "compiled"
    assert out["ranges"] == 1
    assert (rd / "host-agent").exists()
    assert (rd / "iterations" / "01" / "edit-decisions.json").exists()
    assert (rd / "iterations" / "01" / "edl.json").exists()
    assert tuple(Path(out["iteration_dir"]).parts[-2:]) == ("iterations", "01")


def test_host_submit_invalid_payload_returns_blocker(tmp_path):
    rd = _run_dir(tmp_path)
    out = submit_host_decisions(rd, {"cuts": [{"start_s": "not-a-number", "end_s": 1.0}]})
    assert out["status"] == "blocked"
    assert out["blockers"][0]["code"] == "invalid_host_decisions"
