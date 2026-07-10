import hashlib
import json
from pathlib import Path

import pytest

from eddy.pipeline import (
    PipelineRunner,
    _combine_segment_receipts,
    _concat,
    _merge_short_drops,
    _splice,
    _transcribe_final,
    build_render_plan,
    discover_sources,
)
from eddy.plan import EditPlanV3
from eddy.runtime import JobManager, JobState
from test_runtime import valid_plan


def test_discover_sources_prefers_named_camera_and_screen(tmp_path: Path) -> None:
    camera = tmp_path / "webcam.mp4"
    screen = tmp_path / "screen-recording.mp4"
    camera.write_bytes(b"camera")
    screen.write_bytes(b"screen")

    sources = discover_sources(tmp_path)

    assert sources.camera == camera
    assert sources.screen == screen


def test_render_plan_has_one_shared_body_and_three_ranked_outputs(tmp_path: Path) -> None:
    plan = EditPlanV3.from_dict(valid_plan())

    render_plan = build_render_plan(plan, tmp_path)

    assert render_plan.body_cutlist.name == "body-cutlist.json"
    assert [item.output_name for item in render_plan.longs] == [
        "long-primary.mp4",
        "long-alternate-speed.mp4",
        "long-alternate-cost.mp4",
    ]
    body = json.loads(render_plan.body_cutlist.read_text())
    assert body["keep"] == [[5.0, 50.0]]
    drops = json.loads(render_plan.body_dropfile.read_text())
    assert drops["explicit_drops"] == [
        {"span": [0.0, 5.0], "reason": "host_body_drop"},
        {"span": [20.0, 22.0], "reason": "retake_group:repeat-1"},
    ]
    assert all(item.body_cutlist == render_plan.body_cutlist for item in render_plan.longs)


def test_render_plan_uses_snapshot_sources_for_finalization(tmp_path: Path) -> None:
    plan = EditPlanV3.from_dict(valid_plan())
    render_plan = build_render_plan(plan, tmp_path)

    assert render_plan.body_dropfile.parent == tmp_path


def test_short_drops_merge_with_shared_body_drops(tmp_path: Path) -> None:
    payload = valid_plan()
    payload["shorts"][0]["segments"] = [[0.0, 2.0]]
    payload["shorts"][0]["drop"] = [[0.4, 0.8]]
    payload["shorts"][0]["screen_proof_segments"] = [[0.8, 1.4]]
    plan = EditPlanV3.from_dict(payload)
    body_dropfile = tmp_path / "body-drops.json"
    body_dropfile.write_text(
        json.dumps(
            {"explicit_drops": [{"span": [20.0, 22.0], "reason": "shared_body"}]}
        )
    )
    output = tmp_path / "short-drops.json"

    rows = _merge_short_drops(body_dropfile, plan.shorts[0], output)

    assert rows == [
        {"span": [20.0, 22.0], "reason": "shared_body"},
        {"span": [0.4, 0.8], "reason": "host_short_drop:short-0"},
    ]
    assert json.loads(output.read_text())["explicit_drops"] == rows


def test_render_plan_compiles_editorial_resolutions_into_explicit_drops(tmp_path: Path) -> None:
    payload = valid_plan()
    payload["body"]["drop"] = []
    payload["body"]["retake_groups"] = []
    plan = EditPlanV3.from_dict(payload)
    ledger = {
        "candidates": [
            {
                "id": "repeat-1",
                "kind": "repeat",
                "recommended_variant_id": "repeat-1-b",
                "variants": [
                    {"id": "repeat-1-a", "start": 20.0, "end": 22.0},
                    {"id": "repeat-1-b", "start": 24.0, "end": 26.0},
                ],
            }
        ]
    }

    render_plan = build_render_plan(plan, tmp_path, ledger=ledger)

    drops = json.loads(render_plan.body_dropfile.read_text())["explicit_drops"]
    assert drops == [{"span": [20.0, 22.0], "reason": "editorial_candidate:repeat-1"}]


def test_final_verification_transcribes_the_delivered_media(tmp_path: Path, monkeypatch) -> None:
    delivered = tmp_path / "delivered.mp4"
    output = tmp_path / "delivered.words.json"
    captured = []

    def fake_run(command, *, cwd):
        captured.append((command, cwd))

    monkeypatch.setattr("eddy.pipeline._run", fake_run)

    _transcribe_final(tmp_path, delivered, output)

    assert str(delivered) in captured[0][0]
    assert str(output) in captured[0][0]


def test_long_receipt_preserves_hook_then_shared_body_output_order(tmp_path: Path) -> None:
    hook = tmp_path / "hook.segments.json"
    body = tmp_path / "body.segments.json"
    output = tmp_path / "long.segments.json"
    hook.write_text(json.dumps({"segments": [[50.0, 60.0]], "gap_target": 0.1}))
    body.write_text(json.dumps({"segments": [[5.0, 20.0]], "gap_target": 0.1}))

    _combine_segment_receipts(hook, body, output)

    receipt = json.loads(output.read_text())
    assert receipt["segments"] == [[50.0, 60.0], [5.0, 20.0]]
    assert receipt["gap_target"] == 0.1


def test_prepare_reuses_source_hash_transcript_cache(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"immutable-camera")
    manager = JobManager(tmp_path / "runs")
    job = manager.start(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = tmp_path / "cache" / "transcripts" / f"{digest}.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps({"words": [{"word": "proof.", "start": 0.0, "end": 0.5}]}) + "\n"
    )
    monkeypatch.setattr("eddy.pipeline._run", lambda *_args, **_kwargs: pytest.fail("cache miss"))

    PipelineRunner(root=tmp_path, manager=manager).prepare(job.id)

    prepared = manager.load(job.id)
    assert prepared.state is JobState.AWAITING_HOST_PLAN
    assert "transcript_cache_hit" in (prepared.run_dir / "receipts.jsonl").read_text()


def test_v3_splice_disables_legacy_automatic_retake_scan(tmp_path: Path, monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        "eddy.pipeline._run",
        lambda command, *, cwd: captured.append((command, cwd)),
    )

    _splice(
        tmp_path,
        tmp_path / "camera.mp4",
        tmp_path / "transcript.json",
        tmp_path / "cutlist.json",
        tmp_path / "edited.mp4",
    )

    assert "--no-auto-retakes" in captured[0][0]


def test_screen_splice_requests_1080p_normalization(tmp_path: Path, monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        "eddy.pipeline._run",
        lambda command, *, cwd: captured.append((command, cwd)),
    )

    _splice(
        tmp_path,
        tmp_path / "screen.mp4",
        tmp_path / "transcript.json",
        tmp_path / "cutlist.json",
        tmp_path / "edited.mp4",
        scale=(1920, 1080),
        no_audio=True,
    )

    command = captured[0][0]
    assert command[command.index("--scale") + 1] == "1920x1080"


def test_hook_body_concat_preserves_encoded_streams(tmp_path: Path, monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        "eddy.pipeline._run",
        lambda command, *, cwd: captured.append((command, cwd)),
    )

    _concat(tmp_path / "hook.mp4", tmp_path / "body.mp4", tmp_path / "long.mp4")

    command = captured[0][0]
    assert command[command.index("-c") + 1] == "copy"
    assert "-filter_complex" not in command
    assert not (tmp_path / "long.concat.txt").exists()
