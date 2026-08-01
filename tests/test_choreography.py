import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eddy.choreography import (
    ChoreographyValidationError,
    _layout_media_styles,
    build_hyperframes_project,
    rank_opening_candidates,
    validate_frame_contract,
    validate_visual_choreography,
)
from eddy.plan import EditPlanV3, PlanValidationError
from test_runtime import valid_plan_v32


ROOT = Path(__file__).resolve().parents[1]


def test_speaker_close_preserves_presenter_continuity_with_a_subtle_crop() -> None:
    camera, screen = _layout_media_styles(
        "speaker_close",
        width=1920,
        height=1080,
        screen_available=True,
    )

    assert camera["autoAlpha"] == 1
    assert camera["x"] < 0
    assert camera["y"] < 0
    assert camera["width"] > 1920
    assert camera["height"] > 1080
    assert screen["autoAlpha"] == 0


def test_speaker_tight_adds_a_distinct_but_bounded_crop_state() -> None:
    close, _ = _layout_media_styles(
        "speaker_close",
        width=1920,
        height=1080,
        screen_available=True,
    )
    tight, screen = _layout_media_styles(
        "speaker_tight",
        width=1920,
        height=1080,
        screen_available=True,
    )

    assert tight["x"] < close["x"]
    assert tight["y"] < close["y"]
    assert tight["width"] > close["width"]
    assert tight["height"] > close["height"]
    assert screen["autoAlpha"] == 0


def test_opening_ranking_auto_selects_only_with_clear_certain_lead() -> None:
    openings = valid_plan_v32()["visual_choreography"]["openings"]

    result = rank_opening_candidates(openings)

    assert result["status"] == "auto_selected"
    assert result["selected_opening_id"] == "opening-1"
    assert result["score_gap"] == 8.0


def test_opening_ranking_pauses_on_close_or_uncertain_candidates() -> None:
    openings = valid_plan_v32()["visual_choreography"]["openings"]
    openings[1]["ranking_signals"] = dict(openings[0]["ranking_signals"])

    close = rank_opening_candidates(openings)

    assert close["status"] == "selection_required"
    assert close["selected_opening_id"] is None
    openings[1]["ranking_signals"]["taste"] = 0.0
    openings[0]["rank_confidence"] = "uncertain"
    assert rank_opening_candidates(openings)["reason"] == "ranking_uncertain"


def test_hyperframes_compiler_uses_one_paused_timeline_and_full_frame_layouts(
    tmp_path: Path,
) -> None:
    plan = valid_plan_v32()
    scenes = plan["visual_choreography"]["openings"][0]["scenes"]
    scenes[1]["camera_object_position"] = "right center"
    camera = tmp_path / "camera.mp4"
    screen = tmp_path / "screen.mp4"
    camera.write_bytes(b"camera")
    screen.write_bytes(b"screen")

    manifest = build_hyperframes_project(
        tmp_path / "project",
        scenes=scenes,
        camera=camera,
        screen=screen,
        frame_markdown="# Frame\nProof first.\n",
        frame_sha256="d" * 64,
        width=1920,
        height=1080,
    )

    html = (tmp_path / "project" / "index.html").read_text()
    assert html.count("gsap.timeline({paused:true})") == 1
    assert "layout-proof_canvas" in html
    assert "layout-speaker_edge_right" in html
    assert "layout-special_emphasis" in html
    assert html.count("<video") == 2
    assert html.count('id="eddy-camera"') == 1
    assert html.count('id="eddy-screen"') == 1
    assert "scene-1-camera" not in html
    assert "scene-1-screen" not in html
    assert "{autoAlpha:0}" not in html
    assert '"objectPosition": "right center"' in html
    assert "position:absolute" in html
    assert manifest["frame_sha256"] == "d" * 64
    assert len(json.loads((tmp_path / "project" / "animation-map.json").read_text())["scenes"]) == 8


def test_camera_object_position_rejects_unbounded_css_values() -> None:
    plan = valid_plan_v32()
    plan["visual_choreography"]["openings"][0]["scenes"][0][
        "camera_object_position"
    ] = "calc(100% + 1px)"

    with pytest.raises(
        ChoreographyValidationError,
        match="visual_scene_camera_object_position_invalid",
    ):
        validate_visual_choreography(
            plan["visual_choreography"],
            hook_ids=[hook["id"] for hook in plan["hooks"]],
            short_ids=[short["id"] for short in plan["shorts"]],
        )


def test_choreography_render_fake_proves_project_and_audio_mux(tmp_path: Path) -> None:
    camera = tmp_path / "camera.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
            "testsrc2=size=192x108:rate=30:duration=0.6", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=0.6", "-shortest", "-c:v", "libx264",
            "-c:a", "aac", str(camera),
        ],
        check=True,
    )
    frame = tmp_path / "frame.md"
    frame.write_text("# Frame\nProof first.\n")
    scene = valid_plan_v32()["visual_choreography"]["openings"][0]["scenes"][0]
    scene["end"] = 0.5
    brief = tmp_path / "brief.json"
    brief.write_text(
        json.dumps(
            {
                "width": 192,
                "height": 108,
                "camera": str(camera),
                "screen": None,
                "audio_source": str(camera),
                "source_roots": [str(tmp_path)],
                "frame": str(frame),
                "frame_sha256": hashlib.sha256(frame.read_bytes()).hexdigest(),
                "scenes": [scene],
            }
        )
    )
    output = tmp_path / "rendered.mp4"

    command = [
            sys.executable,
            str(ROOT / "scripts" / "choreography_render.py"),
            "--brief", str(brief), "--run-dir", str(tmp_path / "run"),
            "--out", str(output),
        ]
    if not os.environ.get("EDDY_REAL_HYPERFRAMES"):
        command.append("--fake")
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert (tmp_path / "run" / "project" / "choreography-manifest.json").exists()
    assert (tmp_path / "run" / "project" / "provenance.json").exists()
    if os.environ.get("EDDY_REAL_HYPERFRAMES"):
        assert (tmp_path / "run" / "project" / "hyperframes-render.json").exists()


@pytest.mark.parametrize(
    ("contract", "blocker"),
    [
        ({}, "frame_contract_schema_invalid"),
        (
            {"schema_version": "eddy-project-frame-v1", "ref": "../frame.md", "sha256": "d" * 64},
            "frame_contract_ref_invalid",
        ),
        (
            {"schema_version": "eddy-project-frame-v1", "ref": "frame.md", "sha256": "nope"},
            "frame_contract_sha256_invalid",
        ),
    ],
)
def test_frame_contract_fails_closed(contract: dict, blocker: str) -> None:
    with pytest.raises(ChoreographyValidationError, match=blocker):
        validate_frame_contract(contract)


@pytest.mark.parametrize(
    ("motion_verb", "blocker"),
    [
        ("semantic_zoom", "visual_scene_communication_job_required"),
        ("automated_drift", "visual_scene_decorative_camera_move"),
        ("filler_punch_in", "visual_scene_decorative_camera_move"),
    ],
)
def test_camera_movement_requires_a_semantic_job(
    motion_verb: str,
    blocker: str,
) -> None:
    payload = valid_plan_v32()["visual_choreography"]
    payload["openings"][0]["scenes"][0]["motion_verb"] = motion_verb

    with pytest.raises(ChoreographyValidationError, match=blocker):
        validate_visual_choreography(
            payload,
            hook_ids=("proof", "speed", "cost"),
            short_ids=("short-0", "short-1", "short-2"),
        )


def test_v32_rejects_decorative_proof_and_unreasoned_layout_repetition() -> None:
    metaphor = valid_plan_v32()
    metaphor["visual_choreography"]["openings"][0]["scenes"][2][
        "evidence_authority"
    ] = "metaphor"
    metaphor["visual_choreography"]["openings"][0]["scenes"][2][
        "cause"
    ] = "This is explicitly a metaphor, not a receipt."
    with pytest.raises(PlanValidationError, match="opening_real_proof_must_arrive_by_ten_seconds"):
        EditPlanV3.from_dict(metaphor)

    repeated = valid_plan_v32()
    scenes = repeated["visual_choreography"]["shared_body"]["scenes"]
    for scene in scenes[:3]:
        scene["layout"] = "speaker_full"
        scene.pop("quiet_hold_reason", None)
    with pytest.raises(PlanValidationError, match="visual_layout_repeat_limit_exceeded"):
        EditPlanV3.from_dict(repeated)


def test_v32_rejects_bad_ranking_signal_and_excess_brand_wipes() -> None:
    bad_signal = valid_plan_v32()
    bad_signal["visual_choreography"]["openings"][0]["ranking_signals"]["taste"] = 1.1
    with pytest.raises(PlanValidationError, match="opening_ranking_signals_invalid"):
        EditPlanV3.from_dict(bad_signal)

    wipes = valid_plan_v32()
    for scene in wipes["visual_choreography"]["shared_body"]["scenes"][:3]:
        scene["transition"] = "brand_act_wipe"
    with pytest.raises(PlanValidationError, match="long_brand_act_wipe_limit_exceeded"):
        EditPlanV3.from_dict(wipes)


def test_compiler_copies_real_proof_asset_and_hashes_provenance(tmp_path: Path) -> None:
    plan = valid_plan_v32()
    scene = plan["visual_choreography"]["openings"][0]["scenes"][0]
    scene["source_refs"] = ["receipt.png"]
    camera = tmp_path / "camera.mp4"
    receipt = tmp_path / "receipt.png"
    camera.write_bytes(b"camera")
    receipt.write_bytes(b"real proof pixels")

    manifest = build_hyperframes_project(
        tmp_path / "asset-project",
        scenes=[scene],
        camera=camera,
        screen=None,
        frame_markdown="# Frame\n",
        frame_sha256="d" * 64,
        width=1920,
        height=1080,
        source_root=tmp_path,
    )

    assert manifest["asset_sha256"]
    assert (tmp_path / "asset-project" / "scene-asset-1.png").read_bytes() == receipt.read_bytes()
