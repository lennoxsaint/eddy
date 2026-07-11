from __future__ import annotations

import subprocess
import json
from types import SimpleNamespace
from pathlib import Path

from eddy import caption_repair
from eddy.caption_repair import _audio_stream_sha256, _remux_proven_audio
from eddy.runtime import JobManager, JobState, REQUIRED_FINAL_GATES
from test_runtime import valid_plan


def _media(path: Path, *, color: str, frequency: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=160x90:d=0.4:r=25",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration=0.4",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def test_caption_visual_repair_remuxes_proven_audio_without_reencoding(tmp_path: Path) -> None:
    video = tmp_path / "new-video.mp4"
    proven = tmp_path / "proven-audio.mp4"
    output = tmp_path / "repaired.mp4"
    _media(video, color="red", frequency=440)
    _media(proven, color="blue", frequency=880)

    _remux_proven_audio(video, proven, output, cwd=tmp_path)

    assert _audio_stream_sha256(output) == _audio_stream_sha256(proven)
    assert _audio_stream_sha256(output) != _audio_stream_sha256(video)


def test_completed_caption_repair_promotes_only_green_visual_changes(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "camera.mp4").write_bytes(b"camera")
    (source / "screen.mp4").write_bytes(b"screen")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    state = json.loads((job.run_dir / "state.json").read_text())
    state["state"] = JobState.COMPLETED.value
    (job.run_dir / "state.json").write_text(json.dumps(state))

    plan = valid_plan()
    plan["source_hashes"] = json.loads((job.run_dir / "source-lock.json").read_text())["before"]
    (job.run_dir / "edit-plan.json").write_text(json.dumps(plan))
    (job.run_dir / "editorial-ledger.json").write_text(json.dumps({"candidates": []}))
    final = job.run_dir / "final"
    shorts = final / "shorts"
    shorts.mkdir(parents=True)
    for name in ("long-primary.mp4", "long-alternate-a.mp4", "long-alternate-b.mp4"):
        (final / name).write_bytes(name.encode())
    stage = job.run_dir / "work" / "stage-1"
    stage.mkdir(parents=True)
    qa_shorts = []
    for index, short in enumerate(plan["shorts"], start=1):
        short_id = short["id"]
        delivered = shorts / f"{index:02d}-{short_id}.mp4"
        delivered.write_bytes(f"short-{index}".encode())
        for suffix in ("composite.mp4", "motion-overlay.mp4", "camera.segments.json"):
            path = stage / f"short-{short_id}-{suffix}"
            path.write_text(json.dumps({"segments": [[0.0, 1.0]]})) if path.suffix == ".json" else path.write_bytes(b"media")
        (stage / f"short-{short_id}-words.json").write_text(
            json.dumps({"words": [{"word": "Done.", "start": 0.0, "end": 1.0}]})
        )
        (stage / f"short-{short_id}-cutlist.json").write_text(json.dumps({"keep": [[0.0, 1.0]]}))
        qa_shorts.append({"short": short_id, "pass": True})
    (final / "qa.json").write_text(
        json.dumps({"gates": {gate: True for gate in REQUIRED_FINAL_GATES}, "blockers": [], "shorts": qa_shorts})
    )
    (job.run_dir / "verification.json").write_text(
        json.dumps({"gates": {gate: True for gate in REQUIRED_FINAL_GATES}, "blockers": []})
    )
    (final / "provider-receipts.jsonl").write_text("")

    def fake_run(command, *, cwd):
        if "karaoke_ass.py" in " ".join(command):
            proof = Path(command[command.index("--proof-out") + 1])
            proof.write_text(json.dumps({"rendered_tokens": ["Done."]}))
            Path(command[command.index("--out") + 1]).write_text("ASS")
            Path(command[command.index("--video-out") + 1]).write_bytes(b"captioned")

    monkeypatch.setattr(caption_repair, "_run", fake_run)
    monkeypatch.setattr(
        caption_repair,
        "_composite_existing_motion",
        lambda base, overlay, output, cwd: output.write_bytes(b"motioned"),
    )
    monkeypatch.setattr(
        caption_repair,
        "_remux_proven_audio",
        lambda video, proven, output, cwd: output.write_bytes(proven.read_bytes()),
    )
    monkeypatch.setattr(caption_repair, "_audio_stream_sha256", lambda media: "a" * 64)
    monkeypatch.setattr(
        caption_repair,
        "_transcribe_final",
        lambda root, media, output: output.write_text(
            json.dumps({"words": [{"word": "Done.", "start": 0.0, "end": 1.0}]})
        ),
    )
    monkeypatch.setattr(
        caption_repair.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="green", stderr=""),
    )
    monkeypatch.setattr(
        caption_repair,
        "measure_motion_activity",
        lambda *args, **kwargs: {"pass": True, "beats": []},
    )
    monkeypatch.setattr(
        caption_repair,
        "_read_motion_context_proof",
        lambda *args, **kwargs: {"pass": True, "contract": "contextual_skeuomorphic_v1", "beats": []},
    )
    monkeypatch.setattr(
        caption_repair,
        "contextual_motion_verdict",
        lambda *args, **kwargs: {"pass": True},
    )
    monkeypatch.setattr(
        caption_repair,
        "screen_proof_verdict",
        lambda *args, **kwargs: {"pass": True, "screen_share": 1.0, "samples": []},
    )

    result = caption_repair.repair_captions(
        root=Path(__file__).resolve().parents[1], manager=manager, job_id=job.id
    )

    assert result["status"] == "pass", result
    assert result["blockers"] == []
    assert all(row["audio_stream_identical"] for row in result["shorts"])
    assert (job.run_dir / "repairs" / "caption-punctuation-v1" / "originals").exists()
    assert json.loads((final / "qa.json").read_text())["gates"]["caption_terminal_punctuation"]
    assert json.loads((final / "artifact-manifest.json").read_text())["files"]
