import json
import shutil
import subprocess
from pathlib import Path

import pytest

from eddy.pipeline import PipelineRunner
from eddy.runtime import JobManager, JobState


ROOT = Path(__file__).resolve().parents[1]


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
        "body": {"keep": [[0.0, 1.5]], "drop": [], "retake_groups": []},
        "hooks": [
            {"id": "proof", "rank": 1, "segments": [[1.5, 2.0]], "proof_assets": []},
            {"id": "speed", "rank": 2, "segments": [[2.0, 2.5]], "proof_assets": []},
            {"id": "cost", "rank": 3, "segments": [[2.5, 3.0]], "proof_assets": []},
        ],
        "shorts": [
            {"id": "one", "segments": [[0.0, 0.5]]},
            {"id": "two", "segments": [[0.5, 1.0]]},
            {"id": "three", "segments": [[1.0, 1.5]]},
        ],
        "motion_beats": [],
    }
    manager.submit_plan(job.id, plan)
    monkeypatch.setenv("EDDY_FAKE_DESCRIPT", "true")
    monkeypatch.setenv("EDDY_FAKE_HYPERFRAMES", "true")

    PipelineRunner(root=ROOT, manager=manager).finalize(job.id)

    blocked = manager.load(job.id)
    quarantined = blocked.run_dir / "quarantine" / "attempt-1"
    assert blocked.state is JobState.BLOCKED
    assert "descript_test_fixture_not_final" in blocked.blockers
    assert not (blocked.run_dir / "final").exists()
    assert quarantined.exists()
    stage = blocked.run_dir / "work" / "stage-1"
    assert len(list(stage.glob("composite-*.mp4"))) == 3
    assert len(list(stage.glob("motioned-*.mp4"))) == 3
    assert len(list(stage.glob("short-*-captioned.mp4"))) == 3
