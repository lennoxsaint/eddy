"""Semantic visual choreography validation, ranking, and HyperFrames compilation."""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any, Iterable


class ChoreographyValidationError(ValueError):
    """The v3.2+ scene plan cannot produce an honest, paced composition."""


LAYOUTS = {
    "proof_canvas",
    "speaker_full",
    "speaker_close",
    "speaker_tight",
    "speaker_edge_left",
    "speaker_edge_right",
    "speaker_pip",
    "pip_bottom_right",
    "pip_bottom_left",
    "pip_top_right",
    "pip_top_left",
    "vertical_speaker_left",
    "vertical_speaker_right",
    "embedded_split_left",
    "embedded_split_right",
    "speaker_plus_mental_model",
    "speaker_top_screen_bottom",
    "source_screen",
    "illustration_canvas",
    "special_emphasis",
}
EVIDENCE_AUTHORITIES = {
    "raw_source",
    "supplied_asset",
    "pixel_faithful_demo",
    "diagram",
    "metaphor",
}
TRANSITIONS = {
    "hard_cut",
    "continuation_crossfade",
    "semantic_push",
    "scale_match",
    "brand_act_wipe",
}
SEMANTIC_JOBS = {
    "frame_one",
    "money_shot",
    "proof",
    "stakes",
    "explain",
    "context",
    "reset",
    "quote",
}
RANKING_WEIGHTS = {
    "frame_one": 15,
    "money_shot": 20,
    "proof": 20,
    "stakes": 10,
    "muted": 10,
    "mobile": 10,
    "semantic_density": 10,
    "taste": 5,
}


def validate_frame_contract(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChoreographyValidationError("frame_contract_required")
    if value.get("schema_version") not in {
        "eddy-project-frame-v1",
        "eddy-project-frame-v2",
        "eddy-project-frame-v3",
    }:
        raise ChoreographyValidationError("frame_contract_schema_invalid")
    ref = value.get("ref")
    if (
        not isinstance(ref, str)
        or not ref.endswith("frame.md")
        or Path(ref).is_absolute()
        or ".." in Path(ref).parts
    ):
        raise ChoreographyValidationError("frame_contract_ref_invalid")
    digest = value.get("sha256")
    if not _valid_hash(digest):
        raise ChoreographyValidationError("frame_contract_sha256_invalid")
    return dict(value)


def validate_visual_choreography(
    value: object,
    *,
    hook_ids: Iterable[str],
    short_ids: Iterable[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChoreographyValidationError("visual_choreography_required")
    if value.get("schema_version") != "eddy-visual-choreography-v1":
        raise ChoreographyValidationError("visual_choreography_schema_invalid")

    expected_hooks = tuple(hook_ids)
    if not 3 <= len(expected_hooks) <= 6:
        raise ChoreographyValidationError("opening_routes_must_be_3_to_6")
    openings = value.get("openings")
    if not isinstance(openings, list) or len(openings) != len(expected_hooks):
        raise ChoreographyValidationError(
            "opening_choreography_count_must_match_routes"
        )
    opening_hooks: list[str] = []
    opening_ids: list[str] = []
    opening_scene_sets: list[tuple[dict[str, Any], ...]] = []
    for opening in openings:
        if not isinstance(opening, dict):
            raise ChoreographyValidationError("opening_choreography_invalid")
        opening_id = _required_text(opening, "id", "opening_choreography_id_required")
        hook_id = _required_text(opening, "hook_id", "opening_choreography_hook_required")
        _parse_ranking_signals(opening.get("ranking_signals"))
        ranking_evidence = opening.get("ranking_evidence")
        if (
            not isinstance(ranking_evidence, list)
            or not ranking_evidence
            or not all(isinstance(ref, str) and ref.strip() for ref in ranking_evidence)
        ):
            raise ChoreographyValidationError("opening_ranking_evidence_required")
        if opening.get("rank_confidence") not in {"certain", "uncertain"}:
            raise ChoreographyValidationError("opening_rank_confidence_invalid")
        scenes = _parse_scenes(opening.get("scenes"), label=f"opening:{opening_id}")
        _validate_opening(scenes)
        opening_scene_sets.append(scenes)
        opening_ids.append(opening_id)
        opening_hooks.append(hook_id)
    if len(set(opening_ids)) != len(expected_hooks):
        raise ChoreographyValidationError("opening_choreography_ids_must_be_unique")
    if tuple(opening_hooks) != expected_hooks:
        raise ChoreographyValidationError("opening_choreography_hooks_must_match_ranked_hooks")

    shared_body = value.get("shared_body")
    if not isinstance(shared_body, dict) or shared_body.get("id") != "shared-body":
        raise ChoreographyValidationError("shared_body_choreography_required")
    body_scenes = _parse_scenes(shared_body.get("scenes"), label="shared_body")
    _validate_adaptive_cadence(body_scenes, hard_max=12.0, reason_after=8.0)
    body_wipes = sum(scene["transition"] == "brand_act_wipe" for scene in body_scenes)
    if any(
        body_wipes + sum(scene["transition"] == "brand_act_wipe" for scene in scenes) > 2
        for scenes in opening_scene_sets
    ):
        raise ChoreographyValidationError("long_brand_act_wipe_limit_exceeded")

    shorts = value.get("shorts")
    expected_shorts = tuple(short_ids)
    if not isinstance(shorts, list) or len(shorts) != len(expected_shorts):
        raise ChoreographyValidationError("portrait_choreography_required_for_every_short")
    actual_shorts: list[str] = []
    for short in shorts:
        if not isinstance(short, dict):
            raise ChoreographyValidationError("portrait_choreography_invalid")
        short_id = _required_text(short, "short_id", "portrait_choreography_short_id_required")
        scenes = _parse_scenes(short.get("scenes"), label=f"short:{short_id}")
        _validate_short(scenes)
        actual_shorts.append(short_id)
    if tuple(actual_shorts) != expected_shorts:
        raise ChoreographyValidationError("portrait_choreography_ids_must_match_shorts")
    return dict(value)


def rank_opening_candidates(openings: object) -> dict[str, Any]:
    if not isinstance(openings, list) or not 3 <= len(openings) <= 6:
        raise ChoreographyValidationError("opening_routes_must_be_3_to_6")
    rows: list[dict[str, Any]] = []
    for opening in openings:
        if not isinstance(opening, dict):
            continue
        rows.append(
            {
                "opening_id": str(opening["id"]),
                "hook_id": str(opening["hook_id"]),
                "score": _opening_score(opening),
                "confidence": str(opening["rank_confidence"]),
                "evidence": list(opening["ranking_evidence"]),
            }
        )
    rows.sort(key=lambda row: (-float(row["score"]), str(row["opening_id"])))
    if len(rows) != len(openings):
        raise ChoreographyValidationError("opening_choreography_invalid")
    gap = round(float(rows[0]["score"]) - float(rows[1]["score"]), 3)
    uncertain = any(row["confidence"] == "uncertain" for row in rows[:2])
    status = "selection_required" if uncertain or gap <= 5 else "auto_selected"
    reason = "ranking_uncertain" if uncertain else ("top_two_within_five_points" if gap <= 5 else "clear_lead")
    return {
        "schema_version": "eddy-opening-ranking-v1",
        "status": status,
        "reason": reason,
        "selected_opening_id": rows[0]["opening_id"] if status == "auto_selected" else None,
        "score_gap": gap,
        "candidates": rows,
    }


def build_hyperframes_project(
    project: Path,
    *,
    scenes: Iterable[dict[str, Any]],
    camera: Path,
    screen: Path | None,
    frame_markdown: str,
    frame_sha256: str,
    width: int,
    height: int,
    design_markdown: str = "# Project design\n",
    design_sha256: str = "legacy-unbound",
    gsap_source: Path | None = None,
    source_root: Path | None = None,
    source_roots: Iterable[Path] | None = None,
    duration_override: float | None = None,
) -> dict[str, Any]:
    """Compile a seek-safe full-frame project with one paused GSAP timeline."""

    scene_rows = tuple(dict(scene) for scene in scenes)
    if not scene_rows:
        raise ValueError("choreography_scenes_required")
    if duration_override is not None:
        if not math.isfinite(duration_override) or duration_override <= 0:
            raise ValueError("choreography_duration_invalid")
        scene_rows = tuple(
            scene for scene in scene_rows if float(scene["start"]) < duration_override
        )
        if not scene_rows:
            raise ValueError("choreography_scenes_outside_media")
        for scene in scene_rows:
            scene["end"] = min(float(scene["end"]), duration_override)
        scene_rows[-1]["end"] = duration_override
    project.mkdir(parents=True, exist_ok=True)
    camera_name = _link_media(camera, project / f"camera{camera.suffix.lower()}")
    screen_name = _link_media(screen, project / f"screen{screen.suffix.lower()}") if screen else None
    if gsap_source is not None:
        shutil.copy2(gsap_source, project / "gsap.min.js")
    elif not (project / "gsap.min.js").exists():
        (project / "gsap.min.js").write_text("/* supplied by Eddy at render time */\n")

    duration = duration_override or max(float(scene["end"]) for scene in scene_rows)
    portrait = height > width
    scene_markup: list[str] = [
        (
            '<video id="eddy-camera" class="scene-media media-camera" '
            f'src="./{html.escape(camera_name)}" data-start="0" data-duration="{duration:.3f}" '
            'muted playsinline preload="auto"></video>'
        )
    ]
    if screen_name:
        scene_markup.append(
            '<video id="eddy-screen" class="scene-media media-screen" '
            f'src="./{html.escape(screen_name)}" data-start="0" data-duration="{duration:.3f}" '
            'muted playsinline preload="auto"></video>'
        )
    timeline_lines = ["const tl = gsap.timeline({paused:true});"]
    animation_rows: list[dict[str, Any]] = []
    asset_hashes: dict[str, str] = {}
    for index, scene in enumerate(scene_rows):
        scene_id = f"scene-{index + 1}"
        layout = str(scene["layout"])
        start = float(scene["start"])
        end = float(scene["end"])
        transition = str(scene["transition"])
        camera_style, screen_style = _layout_media_styles(
            layout,
            width=width,
            height=height,
            screen_available=screen_name is not None,
        )
        camera_object_position = scene.get("camera_object_position")
        if isinstance(camera_object_position, str):
            camera_style["objectPosition"] = camera_object_position
        asset_roots = tuple(source_roots or (() if source_root is None else (source_root,)))
        asset_name = _copy_scene_asset(
            scene,
            source_roots=asset_roots,
            project=project,
            index=index,
        )
        if asset_name is not None:
            asset_hashes[asset_name] = _sha256(project / asset_name)
        scene_markup.append(
            f'<div id="{scene_id}-state" class="scene-state layout-{html.escape(layout)}" '
            'aria-hidden="true"></div>'
        )
        if asset_name is not None:
            scene_markup.append(
                f'<img id="{scene_id}-asset" class="scene-media proof-asset layout-{html.escape(layout)}" '
                f'src="./{html.escape(asset_name)}" alt="">'
            )
        if transition == "brand_act_wipe":
            scene_markup.append(f'<div id="{scene_id}-wipe" class="brand-wipe"></div>')
        targets: list[str] = []
        if not (start == 0 and camera_style["autoAlpha"] == 0):
            timeline_lines.append(
                f"tl.set('#eddy-camera', {json.dumps(camera_style)}, {start:.3f});"
            )
        if camera_style["autoAlpha"] == 1:
            targets.append("#eddy-camera")
        if screen_name:
            if not (start == 0 and screen_style["autoAlpha"] == 0):
                timeline_lines.append(
                    f"tl.set('#eddy-screen', {json.dumps(screen_style)}, {start:.3f});"
                )
            if screen_style["autoAlpha"] == 1:
                targets.append("#eddy-screen")
        if asset_name is not None:
            targets.append(f"#{scene_id}-asset")
        target_js = json.dumps(targets)
        transform = _motion_from(str(scene["motion_verb"]), transition)
        timeline_lines.append(f"tl.set({target_js}, {{autoAlpha:1}}, {start:.3f});")
        if transition != "hard_cut":
            if camera_style["autoAlpha"] == 1:
                timeline_lines.append(
                    f"tl.fromTo('#eddy-camera', {json.dumps(transform)}, "
                    f"{json.dumps({**camera_style, 'scale': 1, 'duration': 0.32, 'ease': 'power2.out'})}, "
                    f"{start:.3f});"
                )
            if screen_name and screen_style["autoAlpha"] == 1:
                timeline_lines.append(
                    f"tl.fromTo('#eddy-screen', {json.dumps(transform)}, "
                    f"{json.dumps({**screen_style, 'scale': 1, 'duration': 0.32, 'ease': 'power2.out'})}, "
                    f"{start:.3f});"
                )
            if asset_name is not None:
                timeline_lines.append(
                    f"tl.fromTo('#{scene_id}-asset', {json.dumps(transform)}, "
                    f"{{autoAlpha:1,x:0,y:0,scale:1,duration:0.32,ease:'power2.out'}}, {start:.3f});"
                )
        # Shared media persists between adjacent scenes and the next scene's
        # start-state owns its visibility/layout. Hiding shared targets at the
        # exact boundary creates a one-frame blackout when HyperFrames seeks
        # to a hard-cut timestamp. Only scene-local proof assets need an
        # explicit end-state.
        if asset_name is not None:
            timeline_lines.append(
                f"tl.set('#{scene_id}-asset', {{autoAlpha:0}}, {end:.3f});"
            )
        if transition == "brand_act_wipe":
            timeline_lines.append(
                f"tl.fromTo('#{scene_id}-wipe', {{autoAlpha:1,scaleX:0}}, "
                f"{{autoAlpha:1,scaleX:1,duration:0.28,ease:'power2.inOut'}}, {start:.3f});"
            )
            timeline_lines.append(f"tl.set('#{scene_id}-wipe', {{autoAlpha:0}}, {start + 0.32:.3f});")
        animation_rows.append(
            {
                "scene_id": str(scene["id"]),
                "start": start,
                "end": end,
                "layout": layout,
                "motion_verb": str(scene["motion_verb"]),
                "transition": transition,
                "cause": str(scene["cause"]),
            }
        )

    css = _project_css(width=width, height=height, portrait=portrait)
    timeline_lines.append(
        "window.__timelines = window.__timelines || {};"
        "window.__timelines['eddy-choreography'] = tl;"
    )
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{css}</style><script src="./gsap.min.js"></script></head>
<body><div id="stage" data-composition-id="eddy-choreography" data-start="0" data-duration="{duration:.3f}" data-track-index="0" data-width="{width}" data-height="{height}">
{''.join(scene_markup)}
</div><script>{''.join(timeline_lines)}</script></body></html>
"""
    (project / "index.html").write_text(document)
    (project / "hyperframes.json").write_text(json.dumps({"entry": "index.html"}, indent=2) + "\n")
    (project / "design.md").write_text(design_markdown)
    (project / "frame.md").write_text(frame_markdown)
    storyboard = "# Storyboard\n\n" + "\n".join(
        f"- {row['start']:.3f}-{row['end']:.3f}s: {row['layout']} — {row['cause']}"
        for row in animation_rows
    ) + "\n"
    (project / "storyboard.md").write_text(storyboard)
    animation_map = {
        "schema_version": "eddy-hyperframes-animation-map-v1",
        "duration": duration,
        "frame_sha256": frame_sha256,
        "design_sha256": design_sha256,
        "scenes": animation_rows,
    }
    (project / "animation-map.json").write_text(json.dumps(animation_map, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema_version": "eddy-choreography-manifest-v1",
        "duration": duration,
        "width": width,
        "height": height,
        "frame_sha256": frame_sha256,
        "camera_sha256": _sha256(camera),
        "screen_sha256": _sha256(screen) if screen else None,
        "asset_sha256": asset_hashes,
        "scene_count": len(scene_rows),
        "animation_map": "animation-map.json",
    }
    (project / "choreography-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _parse_scenes(value: object, *, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or not value:
        raise ChoreographyValidationError(f"visual_scenes_required:{label}")
    scenes: list[dict[str, Any]] = []
    ids: set[str] = set()
    prior_start = -1.0
    for raw in value:
        if not isinstance(raw, dict):
            raise ChoreographyValidationError(f"visual_scene_invalid:{label}")
        scene_id = _required_text(raw, "id", f"visual_scene_id_required:{label}")
        if scene_id in ids:
            raise ChoreographyValidationError(f"visual_scene_ids_must_be_unique:{label}")
        ids.add(scene_id)
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ChoreographyValidationError(f"visual_scene_timing_invalid:{label}") from exc
        if not all(math.isfinite(item) for item in (start, end)) or start < 0 or end <= start:
            raise ChoreographyValidationError(f"visual_scene_timing_invalid:{label}")
        if start < prior_start:
            raise ChoreographyValidationError(f"visual_scenes_must_be_sorted:{label}")
        prior_start = start
        for field in ("speech_anchor", "meaningful_change", "motion_verb", "cause"):
            _required_text(raw, field, f"visual_scene_{field}_required:{label}")
        motion_verb = str(raw["motion_verb"]).strip().lower()
        if motion_verb in {"automated_drift", "filler_punch_in"}:
            raise ChoreographyValidationError(f"visual_scene_decorative_camera_move:{label}")
        if any(token in motion_verb for token in ("zoom", "push_in", "punch_in")):
            _required_text(
                raw,
                "communication_job",
                f"visual_scene_communication_job_required:{label}",
            )
        if raw.get("semantic_job") not in SEMANTIC_JOBS:
            raise ChoreographyValidationError(f"visual_scene_semantic_job_invalid:{label}")
        if raw.get("layout") not in LAYOUTS:
            raise ChoreographyValidationError(f"visual_scene_layout_invalid:{label}")
        if raw.get("evidence_authority") not in EVIDENCE_AUTHORITIES:
            raise ChoreographyValidationError(f"visual_scene_evidence_authority_invalid:{label}")
        if raw.get("transition") not in TRANSITIONS:
            raise ChoreographyValidationError(f"visual_scene_transition_invalid:{label}")
        refs = raw.get("source_refs")
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref for ref in refs):
            raise ChoreographyValidationError(f"visual_scene_source_refs_required:{label}")
        if not isinstance(raw.get("preview_safe"), bool):
            raise ChoreographyValidationError(f"visual_scene_preview_safe_required:{label}")
        camera_object_position = raw.get("camera_object_position")
        if camera_object_position is not None and camera_object_position not in {
            "left center",
            "center center",
            "right center",
        }:
            raise ChoreographyValidationError(
                f"visual_scene_camera_object_position_invalid:{label}"
            )
        scenes.append(dict(raw))
    _validate_layout_repetition(tuple(scenes))
    for left, right in zip(scenes, scenes[1:], strict=False):
        if float(right["start"]) - float(left["end"]) > 0.1:
            raise ChoreographyValidationError(f"visual_scene_gap_exceeds_point_one:{label}")
    for scene in scenes:
        if (
            scene["evidence_authority"] == "metaphor"
            and "metaphor" not in str(scene["cause"]).lower()
        ):
            raise ChoreographyValidationError(f"visual_metaphor_must_be_clearly_framed:{label}")
    return tuple(scenes)


def _validate_opening(scenes: tuple[dict[str, Any], ...]) -> None:
    first_thirty = tuple(scene for scene in scenes if float(scene["start"]) < 30)
    if not 8 <= len(first_thirty) <= 12:
        raise ChoreographyValidationError("opening_eight_to_twelve_meaningful_changes_required")
    if float(first_thirty[0]["start"]) > 0.04 or first_thirty[0]["semantic_job"] != "frame_one":
        raise ChoreographyValidationError("opening_frame_one_activity_required")
    _require_job_by(first_thirty, "money_shot", 3.0, "opening_money_shot_must_arrive_by_three_seconds")
    if not any(
        scene["semantic_job"] == "proof"
        and float(scene["start"]) <= 10
        and scene["evidence_authority"]
        in {"raw_source", "supplied_asset", "pixel_faithful_demo"}
        for scene in first_thirty
    ):
        raise ChoreographyValidationError("opening_real_proof_must_arrive_by_ten_seconds")
    _require_job_by(first_thirty, "stakes", 30.0, "opening_stakes_must_arrive_by_thirty_seconds")
    if len({str(scene["layout"]) for scene in first_thirty}) < 3:
        raise ChoreographyValidationError("opening_three_layout_states_required")
    if not all(bool(scene["preview_safe"]) for scene in first_thirty):
        raise ChoreographyValidationError("opening_scene_not_preview_safe")
    for scene in first_thirty:
        hold = float(scene["end"]) - float(scene["start"])
        if hold > 4 and not _optional_reason(scene):
            raise ChoreographyValidationError("opening_unexplained_static_hold_exceeds_four_seconds")
    if sum(scene["transition"] == "brand_act_wipe" for scene in scenes) > 2:
        raise ChoreographyValidationError("long_brand_act_wipe_limit_exceeded")
    _validate_adaptive_cadence(scenes, hard_max=12.0, reason_after=8.0)


def _validate_short(scenes: tuple[dict[str, Any], ...]) -> None:
    if float(scenes[0]["start"]) > 0.04 or scenes[0]["semantic_job"] != "frame_one":
        raise ChoreographyValidationError("short_frame_one_activity_required")
    _require_job_by(scenes, "money_shot", 3.0, "short_money_shot_must_arrive_by_three_seconds")
    first_thirty = tuple(scene for scene in scenes if float(scene["start"]) < 30)
    expected = min(8, max(3, math.ceil(min(30.0, float(scenes[-1]["end"])) / 4)))
    if len(first_thirty) < expected:
        raise ChoreographyValidationError("short_opening_change_density_too_low")
    _validate_adaptive_cadence(scenes, hard_max=8.0, reason_after=8.0)
    if sum(scene["transition"] == "brand_act_wipe" for scene in scenes) > 1:
        raise ChoreographyValidationError("short_brand_act_wipe_limit_exceeded")


def _validate_adaptive_cadence(
    scenes: tuple[dict[str, Any], ...], *, hard_max: float, reason_after: float
) -> None:
    for left, right in zip(scenes, scenes[1:], strict=False):
        gap = float(right["start"]) - float(left["start"])
        if gap > hard_max:
            raise ChoreographyValidationError("visual_state_change_exceeds_twelve_seconds")
        if gap > reason_after and not _optional_reason(left):
            raise ChoreographyValidationError("visual_hold_reason_required_after_eight_seconds")


def _validate_layout_repetition(scenes: tuple[dict[str, Any], ...]) -> None:
    for index in range(2, len(scenes)):
        layouts = {str(scenes[index - offset]["layout"]) for offset in range(3)}
        if len(layouts) == 1 and not _optional_reason(scenes[index - 1]):
            raise ChoreographyValidationError("visual_layout_repeat_limit_exceeded")


def _require_job_by(
    scenes: Iterable[dict[str, Any]], job: str, deadline: float, blocker: str
) -> None:
    if not any(scene["semantic_job"] == job and float(scene["start"]) <= deadline for scene in scenes):
        raise ChoreographyValidationError(blocker)


def _required_text(value: dict[str, Any], field: str, blocker: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise ChoreographyValidationError(blocker)
    return result.strip()


def _parse_ranking_signals(value: object) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(RANKING_WEIGHTS):
        raise ChoreographyValidationError("opening_ranking_signals_invalid")
    parsed: dict[str, float] = {}
    for key in RANKING_WEIGHTS:
        raw = value[key]
        if (
            not isinstance(raw, (int, float))
            or isinstance(raw, bool)
            or not math.isfinite(float(raw))
            or not 0 <= float(raw) <= 1
        ):
            raise ChoreographyValidationError("opening_ranking_signals_invalid")
        parsed[key] = float(raw)
    return parsed


def _opening_score(opening: dict[str, Any]) -> float:
    signals = _parse_ranking_signals(opening.get("ranking_signals"))
    return round(
        sum(signals[key] * weight for key, weight in RANKING_WEIGHTS.items()),
        3,
    )


def _optional_reason(scene: dict[str, Any]) -> bool:
    reason = scene.get("quiet_hold_reason")
    return isinstance(reason, str) and bool(reason.strip())


def _valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _link_media(source: Path | None, destination: Path) -> str:
    if source is None:
        raise ValueError("choreography_media_missing")
    source = source.resolve()
    destination.unlink(missing_ok=True)
    try:
        os.symlink(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return destination.name


def _copy_scene_asset(
    scene: dict[str, Any],
    *,
    source_roots: tuple[Path, ...],
    project: Path,
    index: int,
) -> str | None:
    if not source_roots:
        return None
    for raw_ref in scene.get("source_refs", []):
        ref = Path(str(raw_ref))
        if ref.is_absolute() or ".." in ref.parts:
            continue
        for raw_root in source_roots:
            root = raw_root.resolve()
            source = (root / ref).resolve()
            try:
                source.relative_to(root)
            except ValueError:
                continue
            if (
                not source.is_file()
                or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
            ):
                continue
            name = f"scene-asset-{index + 1}{source.suffix.lower()}"
            shutil.copy2(source, project / name)
            return name
    return None


def _sha256(path: Path | None) -> str:
    if path is None:
        raise ValueError("choreography_media_missing")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _layout_media_styles(
    layout: str,
    *,
    width: int,
    height: int,
    screen_available: bool,
) -> tuple[dict[str, float | int | str], dict[str, float | int | str]]:
    """Return seek-safe GSAP styles for one shared camera/screen pair.

    HyperFrames discovers every video element in the composition. Repeating the
    same 1080p camera and screen element per scene multiplied decoder pressure
    and could close the browser session on a 60-second opening. One shared pair
    keeps media discovery bounded while the timeline changes layout state.
    """

    full: dict[str, float | int | str] = {
        "x": 0,
        "y": 0,
        "width": width,
        "height": height,
        "borderRadius": 0,
        "borderWidth": 0,
        "autoAlpha": 1,
    }
    hidden: dict[str, float | int | str] = {**full, "autoAlpha": 0}
    screen_style: dict[str, float | int | str] = (
        hidden
        if layout in {"speaker_full", "speaker_close", "speaker_tight"}
        else {**full, "zIndex": 1}
    )
    if layout in {"speaker_close", "speaker_tight"}:
        crop_ratio = 0.04 if layout == "speaker_close" else 0.07
        crop_x = round(width * crop_ratio)
        crop_y = round(height * crop_ratio)
        return (
            {
                **full,
                "x": -crop_x,
                "y": -crop_y,
                "width": width + crop_x * 2,
                "height": height + crop_y * 2,
                "zIndex": 2,
            },
            screen_style,
        )
    if layout == "speaker_full" or not screen_available:
        return {**full, "zIndex": 2}, screen_style
    if layout in {"speaker_edge_left", "speaker_edge_right"}:
        edge_width = round(width * 0.31)
        return (
            {
                **full,
                "x": 0 if layout == "speaker_edge_left" else width - edge_width,
                "width": edge_width,
                "zIndex": 3,
            },
            screen_style,
        )
    if layout == "speaker_pip":
        pip_width = round(width * 0.25)
        pip_height = round(height * 0.39)
        return (
            {
                **full,
                "x": width - pip_width - round(width * 0.04),
                "y": height - pip_height - round(height * 0.06),
                "width": pip_width,
                "height": pip_height,
                "borderRadius": 24,
                "borderWidth": 2,
                "zIndex": 3,
            },
            screen_style,
        )
    if layout == "special_emphasis":
        circle_width = round(width * 0.30)
        circle_height = round(height * 0.53)
        return (
            {
                **full,
                "x": width - circle_width - round(width * 0.05),
                "y": height - circle_height - round(height * 0.07),
                "width": circle_width,
                "height": circle_height,
                "borderRadius": 999,
                "borderWidth": 5,
                "zIndex": 3,
            },
            screen_style,
        )
    return hidden, screen_style


def _motion_from(motion_verb: str, transition: str) -> dict[str, float | int]:
    if transition == "semantic_push":
        return {"autoAlpha": 0, "x": 90, "y": 0, "scale": 1}
    if transition == "scale_match":
        return {"autoAlpha": 0, "x": 0, "y": 0, "scale": 0.86}
    if motion_verb in {"push", "slide"}:
        return {"autoAlpha": 0, "x": 64, "y": 0, "scale": 1}
    if motion_verb in {"lift", "rise"}:
        return {"autoAlpha": 0, "x": 0, "y": 48, "scale": 1}
    if motion_verb in {"scale", "expand"}:
        return {"autoAlpha": 0, "x": 0, "y": 0, "scale": 0.9}
    if transition == "continuation_crossfade":
        return {"autoAlpha": 0, "x": 0, "y": 0, "scale": 1}
    return {"autoAlpha": 0, "x": 0, "y": 0, "scale": 1}


def _project_css(*, width: int, height: int, portrait: bool) -> str:
    return f"""
*{{box-sizing:border-box}}html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:#05070b}}
#stage{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:#05070b}}
.scene-media,.brand-wipe{{position:absolute;opacity:0;visibility:hidden;will-change:transform,opacity}}
.scene-media{{left:0;top:0;width:100%;height:100%;object-fit:cover;border-style:solid;border-color:rgba(255,255,255,.72)}}
.scene-state{{display:none}}
.media-screen{{object-fit:cover;z-index:1}}
.media-camera{{z-index:2;object-fit:cover;box-shadow:0 18px 60px #000}}
.proof-asset{{z-index:2;object-fit:contain;background:#05070b;padding:{0 if not portrait else 24}px}}
.brand-wipe{{z-index:10;inset:0;background:#d9b45b;transform-origin:left center}}
"""
