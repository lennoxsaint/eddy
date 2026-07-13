import json
import shutil
import subprocess
from pathlib import Path

import pytest

import eddy.pipeline as pipeline
from eddy.pipeline import (
    PipelineRunner,
    _descript_failure_blocker,
    _delivered_gap_violations,
    _repair_delivered_cadence,
)
from eddy.runtime import JobManager, JobState


ROOT = Path(__file__).resolve().parents[1]


def test_delivered_gap_repair_targets_only_outliers(tmp_path: Path) -> None:
    transcript = tmp_path / "words.json"
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    {"word": "one", "start": 0.0, "end": 0.1},
                    {"word": "two", "start": 0.25, "end": 0.35},
                    {"word": "three", "start": 1.25, "end": 1.35},
                ]
            }
        )
        + "\n"
    )

    assert _delivered_gap_violations(transcript) == [[0.35, 1.25]]


def test_descript_failure_blocker_distinguishes_provider_timeout() -> None:
    stderr = json.dumps(
        {"event": "error", "error": "descript_job_timeout:job-id"}
    )

    assert _descript_failure_blocker(stderr) == "descript_provider_timeout"


def test_descript_failure_blocker_reports_agent_misroute_not_voice_consent() -> None:
    stderr = json.dumps(
        {"event": "error", "error": "descript_studio_sound_agent_misrouted"}
    )

    assert _descript_failure_blocker(stderr) == "descript_studio_sound_agent_misrouted"


def test_descript_failure_blocker_keeps_effect_survival_reason() -> None:
    stderr = json.dumps(
        {
            "event": "descript_effect_survival",
            "status": "failed",
            "blockers": ["descript_effect_not_rendered"],
        }
    )

    assert _descript_failure_blocker(stderr) == "descript_effect_not_rendered"


def test_delivered_cadence_repair_replaces_media_and_writes_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    media = tmp_path / "long.mp4"
    media.write_bytes(b"before")
    words = tmp_path / "words.json"
    words.write_text(
        json.dumps(
            {
                "words": [
                    {"word": "one", "start": 0.0, "end": 0.1},
                    {"word": "two", "start": 1.0, "end": 1.1},
                ]
            }
        )
        + "\n"
    )
    work = tmp_path / "stage"
    work.mkdir()
    receipts = tmp_path / "provider-receipts.jsonl"
    transcribed: list[Path] = []

    def fake_splice(
        root: Path,
        source: Path,
        transcript: Path,
        cutlist: Path,
        output: Path,
        **kwargs,
    ) -> None:
        assert source == media
        assert transcript == words
        assert json.loads(cutlist.read_text())["keep"] == [[0.0, 1.2]]
        output.write_bytes(b"after")
        output.with_name(f"{output.stem}.segments.json").write_text(
            json.dumps({"segments": [[0.0, 0.2], [0.6, 1.0]]}) + "\n"
        )

    monkeypatch.setattr(pipeline, "_media_duration", lambda path: 1.2)
    monkeypatch.setattr(pipeline, "_splice", fake_splice)
    def fake_transcribe(root: Path, path: Path, output: Path) -> None:
        transcribed.append(path)
        output.write_text(
            json.dumps(
                {
                    "words": [
                        {"word": "one", "start": 0.0, "end": 0.1},
                        {"word": "two", "start": 0.2, "end": 0.3},
                    ]
                }
            )
            + "\n"
        )

    monkeypatch.setattr(pipeline, "_transcribe_final", fake_transcribe)

    repaired = _repair_delivered_cadence(
        tmp_path,
        media,
        words,
        work,
        label="long-1",
        receipts=receipts,
        artifact="long-primary.mp4",
    )

    row = json.loads(receipts.read_text())
    assert repaired is True
    assert media.read_bytes() == b"after"
    assert row["event"] == "post_descript_cadence_repair"
    assert row["pass"] == 1
    assert row["violations_after"] == []
    assert row["before_sha256"] != row["output_sha256"]
    assert transcribed == [media]


def test_delivered_cadence_repair_stops_when_violation_count_does_not_improve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    work = tmp_path / "work"
    work.mkdir()
    media = work / "long-primary.mp4"
    media.write_bytes(b"before")
    words = work / "long-primary.words.json"
    words.write_text(
        json.dumps(
            {
                "words": [
                    {"word": "one", "start": 0.0, "end": 0.1},
                    {"word": "two", "start": 1.0, "end": 1.1},
                ]
            }
        )
        + "\n"
    )
    receipts = tmp_path / "receipts.jsonl"
    splice_calls: list[Path] = []

    def fake_splice(
        root: Path,
        source: Path,
        transcript: Path,
        cutlist: Path,
        output: Path,
    ) -> None:
        splice_calls.append(output)
        output.write_bytes(b"after")
        output.with_name(f"{output.stem}.segments.json").write_text(
            json.dumps({"segments": [[0.0, 1.2]]}) + "\n"
        )

    monkeypatch.setattr(pipeline, "_media_duration", lambda path: 1.2)
    monkeypatch.setattr(pipeline, "_splice", fake_splice)
    monkeypatch.setattr(pipeline, "_transcribe_final", lambda root, path, output: None)

    repaired = _repair_delivered_cadence(
        root,
        media,
        words,
        work,
        label="long-primary",
        receipts=receipts,
        artifact="long-primary",
    )

    rows = [json.loads(line) for line in receipts.read_text().splitlines()]
    assert repaired is True
    assert len(splice_calls) == 1
    assert rows[0]["status"] == "no_progress"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_talking_head_pipeline_renders_three_shared_body_longs(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    camera = source / "camera.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
            "testsrc2=size=320x180:rate=30:duration=4", "-f", "lavfi", "-i",
            "sine=frequency=220:sample_rate=48000:duration=4", "-c:v", "libx264", "-pix_fmt",
            "yuv420p", "-c:a", "aac", "-shortest", str(camera),
        ],
        check=True,
    )
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    job = manager.transition(job.id, JobState.AWAITING_HOST_PLAN)
    words = [
        {"word": f"w{i}", "start": round(i * 0.1, 2), "end": round(i * 0.1 + 0.08, 2)}
        for i in range(38)
    ]
    (job.run_dir / "transcript.json").write_text(json.dumps({"words": words}) + "\n")
    lock = json.loads((job.run_dir / "source-lock.json").read_text())
    plan = {
        "schema_version": "edit-plan-v3",
        "source_hashes": lock["before"],
        "protected": [],
        "editorial_review": {"coverage": [[0.0, 4.0]], "resolutions": []},
        "body": {"keep": [[0.0, 1.5]], "drop": [], "retake_groups": []},
        "hooks": [
            {"id": "proof", "rank": 1, "segments": [[1.5, 2.0]], "proof_assets": []},
            {"id": "speed", "rank": 2, "segments": [[2.0, 2.5]], "proof_assets": []},
            {"id": "cost", "rank": 3, "segments": [[2.5, 3.0]], "proof_assets": []},
        ],
        "shorts": [
            {
                "id": short_id,
                "segments": [[start, start + 0.5]],
                "screen_proof_segments": [],
                "motion_beats": [
                    {"id": "hook", "start": 0.0, "dur": 0.1, "layout": "stat", "label": "HOOK"},
                    {"id": "proof", "start": 0.3, "dur": 0.1, "layout": "stat", "label": "PROOF"},
                ],
            }
            for short_id, start in (("one", 0.0), ("two", 0.5), ("three", 1.0))
        ],
        "motion_beats": [
            {
                "id": "long-hook",
                "hook_id": "*",
                "start": 0.0,
                "dur": 0.4,
                "layout": "kinetic_hook",
                "label": "HOOK",
            },
            {
                "id": "long-proof",
                "hook_id": "*",
                "start": 0.6,
                "dur": 0.4,
                "layout": "proof_callout",
                "label": "PROOF",
            },
        ],
    }
    manager.submit_plan(job.id, plan)
    monkeypatch.setenv("EDDY_FAKE_DESCRIPT", "true")
    monkeypatch.setenv("EDDY_FAKE_HYPERFRAMES", "true")

    PipelineRunner(root=ROOT, manager=manager).finalize(job.id)

    repair = manager.load(job.id)
    quarantined = repair.run_dir / "quarantine" / "attempt-1"
    assert repair.state is JobState.AWAITING_HOST_REPAIR
    assert "descript_test_fixture_not_final" in repair.blockers
    assert not (repair.run_dir / "final").exists()
    assert quarantined.exists()
    stage = repair.run_dir / "work" / "stage-1"
    assert (stage / "body-composite.mp4").exists()
    assert len(list(stage.glob("composite-*.mp4"))) == 1
    assert len(list(stage.glob("motioned-*.mp4"))) == 1
    assert len(list(stage.glob("short-*-captioned.mp4"))) == 0
