import json
from pathlib import Path

from eddy.pipeline import build_render_plan, discover_sources
from eddy.plan import EditPlanV3
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
    assert all(item.body_cutlist == render_plan.body_cutlist for item in render_plan.longs)
