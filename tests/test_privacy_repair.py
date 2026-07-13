from __future__ import annotations

import json
import subprocess
from pathlib import Path

from eddy.caption_repair import _audio_stream_sha256
from eddy.privacy_repair import repair_short_privacy
from eddy.runtime import JobManager, JobState


def _media(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=1080x1920:d=0.5:r=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.5",
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def test_completed_short_privacy_repair_preserves_longs_and_proven_audio(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"raw-camera")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    state = json.loads((job.run_dir / "state.json").read_text())
    state["state"] = JobState.COMPLETED.value
    (job.run_dir / "state.json").write_text(json.dumps(state))

    final = job.run_dir / "final"
    shorts = final / "shorts"
    shorts.mkdir(parents=True)
    for name in ("long-primary.mp4", "long-alternate-a.mp4", "long-alternate-b.mp4"):
        (final / name).write_bytes(name.encode())
    delivered = shorts / "03-theft.mp4"
    _media(delivered)
    audio_before = _audio_stream_sha256(delivered)
    (final / "qa.json").write_text(
        json.dumps({"gates": {}, "blockers": [], "shorts": [{"short": "theft", "pass": True}]})
    )
    (job.run_dir / "verification.json").write_text(
        json.dumps({"gates": {}, "blockers": []})
    )
    (final / "provider-receipts.jsonl").write_text("")

    result = repair_short_privacy(
        root=Path(__file__).resolve().parents[1],
        manager=manager,
        job_id=job.id,
        payload={
            "schema_version": "privacy-repair-v1",
            "repairs": [
                {
                    "artifact": "shorts/03-theft.mp4",
                    "masks": [
                        {
                            "id": "bystander-comments",
                            "start": 0.0,
                            "end": 0.4,
                            "x": 0,
                            "y": 1750,
                            "width": 1080,
                            "height": 170,
                            "color": "0x111827",
                        }
                    ],
                }
            ],
        },
    )

    assert result["status"] == "pass", result
    assert result["long_hashes_before"] == result["long_hashes_after"]
    assert result["repairs"][0]["audio_stream_identical"] is True
    assert all(proof["pass"] for proof in result["repairs"][0]["visual_proof"])
    assert _audio_stream_sha256(delivered) == audio_before
    assert (job.run_dir / "repairs" / "privacy-v1" / "originals" / "shorts" / "03-theft.mp4").exists()
    qa = json.loads((final / "qa.json").read_text())
    assert qa["gates"]["shorts_privacy_masks"] is True
    assert qa["shorts"][0]["privacy_masks"][0]["id"] == "bystander-comments"


def test_short_privacy_repair_rejects_escape_and_out_of_bounds_masks(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    state = json.loads((job.run_dir / "state.json").read_text())
    state["state"] = JobState.COMPLETED.value
    (job.run_dir / "state.json").write_text(json.dumps(state))
    (job.run_dir / "final").mkdir()

    for artifact, x in (("../escape.mp4", 0), ("shorts/missing.mp4", 1080)):
        try:
            repair_short_privacy(
                root=Path(__file__).resolve().parents[1],
                manager=manager,
                job_id=job.id,
                payload={
                    "schema_version": "privacy-repair-v1",
                    "repairs": [
                        {
                            "artifact": artifact,
                            "masks": [
                                {
                                    "id": "mask",
                                    "start": 0,
                                    "end": 1,
                                    "x": x,
                                    "y": 0,
                                    "width": 1,
                                    "height": 1,
                                    "color": "0x111827",
                                }
                            ],
                        }
                    ],
                },
            )
        except (ValueError, FileNotFoundError):
            pass
        else:
            raise AssertionError("unsafe privacy repair must fail")
