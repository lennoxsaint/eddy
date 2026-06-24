"""Template registry for Eddy's one-sentence editing flow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Mapping
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TemplateContract:
    """A compact contract for an edit archetype Eddy can execute."""

    id: str
    label: str
    description: str
    requires: tuple[str, ...]
    outputs: tuple[str, ...]
    long_layout: str
    shorts_layout: str
    captions: str
    motion: str
    audio: str
    qa_gates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_REGISTRY: dict[str, TemplateContract] = {
    "talking_head_screen_tutorial": TemplateContract(
        id="talking_head_screen_tutorial",
        label="Talking head screen tutorial",
        description=(
            "Best for a creator teaching through a screen recording with a separate "
            "camera layer, long-form retention cuts, motion graphics, and Shorts."
        ),
        requires=("screen", "camera"),
        outputs=("youtube_long", "shorts", "motion_graphics", "studio_sound"),
        long_layout="screen-primary with rounded camera picture-in-picture",
        shorts_layout=(
            "large rounded-square camera top, black karaoke caption strip, "
            "uncropped screen/proof panel bottom"
        ),
        captions="one-line karaoke captions for Shorts; long captions optional",
        motion="HyperFrames frame.md + storyboard.md + storyboard.html contract",
        audio="heavy local Studio Sound profile with click repair and loudness proof",
        qa_gates=(
            "source_lock",
            "studio_sound",
            "retake_scan",
            "silence_scan",
            "blinkless_cuts",
            "motion_collision",
            "shorts_layout_lock",
            "support_bundle_on_failure",
        ),
    ),
    "single_camera_course": TemplateContract(
        id="single_camera_course",
        label="Single camera course or monologue",
        description=(
            "Best for one camera/video file when no separate screen recording is present. "
            "Eddy still performs retention editing, audio cleanup, captions, and QA."
        ),
        requires=("camera",),
        outputs=("youtube_long", "shorts", "studio_sound"),
        long_layout="full-frame camera with tasteful proof/title overlays when useful",
        shorts_layout="large rounded-square camera top with karaoke caption strip",
        captions="one-line karaoke captions for Shorts",
        motion="optional HyperFrames proof/title overlays when storyboard evidence exists",
        audio="heavy local Studio Sound profile with click repair and loudness proof",
        qa_gates=(
            "source_lock",
            "studio_sound",
            "retake_scan",
            "silence_scan",
            "blinkless_cuts",
            "shorts_layout_lock",
            "support_bundle_on_failure",
        ),
    ),
    "screen_only_demo": TemplateContract(
        id="screen_only_demo",
        label="Screen-only demo",
        description=(
            "Best for a screen recording with voiceover but no camera layer. Eddy avoids "
            "fake picture-in-picture work and focuses on proof visibility."
        ),
        requires=("screen",),
        outputs=("youtube_long", "shorts", "motion_graphics", "studio_sound"),
        long_layout="screen-primary with zooms and HyperFrames proof overlays",
        shorts_layout="screen/proof panel with karaoke caption strip and safe zooms",
        captions="one-line karaoke captions for Shorts",
        motion="HyperFrames frame.md + storyboard.md + storyboard.html contract",
        audio="heavy local Studio Sound profile with click repair and loudness proof",
        qa_gates=(
            "source_lock",
            "studio_sound",
            "retake_scan",
            "silence_scan",
            "blinkless_cuts",
            "motion_collision",
            "shorts_layout_lock",
            "support_bundle_on_failure",
        ),
    ),
}


def template_registry() -> dict[str, TemplateContract]:
    return dict(_REGISTRY)


def get_template(template_id: str) -> TemplateContract:
    try:
        return _REGISTRY[template_id]
    except KeyError as exc:
        valid = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown Eddy template '{template_id}'. Valid templates: {valid}") from exc


def select_template(
    sources: Mapping[str, str | Path],
    *,
    requested: str | None = None,
    focus: str | None = None,
) -> TemplateContract:
    """Select the most specific template that matches discovered source layers."""

    if requested:
        template = get_template(requested)
        missing = [key for key in template.requires if key not in sources]
        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(f"Template '{requested}' needs missing source layer(s): {missing_text}")
        return template

    source_keys = set(sources)
    focus_text = (focus or "").lower()
    if {"screen", "camera"}.issubset(source_keys):
        return _REGISTRY["talking_head_screen_tutorial"]
    if "screen" in source_keys and "camera" not in source_keys:
        return _REGISTRY["screen_only_demo"]
    if "camera" in source_keys:
        return _REGISTRY["single_camera_course"]
    if "tutorial" in focus_text or "demo" in focus_text:
        return _REGISTRY["screen_only_demo"]
    return _REGISTRY["single_camera_course"]


def template_inventory() -> list[dict[str, Any]]:
    return [template.to_dict() for template in _REGISTRY.values()]
