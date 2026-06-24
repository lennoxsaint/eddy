"""Bootstrap and repair planning for Eddy installs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RepairAction:
    id: str
    title: str
    reason: str
    command: str | None
    automatic: bool
    requires_approval: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def repair_actions(checks: list[dict[str, Any]]) -> list[RepairAction]:
    """Map preflight failures into honest, user-reviewable repair actions."""

    actions: list[RepairAction] = []
    by_name = {str(check.get("check") or check.get("name")): check for check in checks}

    if not by_name.get("ffmpeg", {}).get("ok", False):
        actions.append(
            RepairAction(
                id="install_ffmpeg",
                title="Install ffmpeg and ffprobe",
                reason="Eddy cannot inspect, trim, render, or QA videos without ffmpeg and ffprobe.",
                command="brew install ffmpeg",
                automatic=False,
                requires_approval=False,
            )
        )

    if not by_name.get("video encoder", {}).get("ok", False):
        actions.append(
            RepairAction(
                id="enable_video_encoder",
                title="Enable a usable H.264 encoder",
                reason="Eddy found ffmpeg but no usable H.264 encoder for review-ready outputs.",
                command="eddy doctor --no-write",
                automatic=False,
                requires_approval=False,
            )
        )

    if not by_name.get("studio sound", {}).get("ok", False):
        actions.append(
            RepairAction(
                id="install_studio_sound_backend",
                title="Install Eddy Studio Sound backend",
                reason="Eddy needs the heavy local voice-enhancement path before it can promise clean audio.",
                command="eddy studio-sound install --backend deepfilternet",
                automatic=False,
                requires_approval=False,
            )
        )

    if not by_name.get("free disk", {}).get("ok", False):
        actions.append(
            RepairAction(
                id="free_disk_space",
                title="Free disk space",
                reason="Video renders need enough temporary space for stable intermediates and support bundles.",
                command=None,
                automatic=False,
                requires_approval=True,
            )
        )

    return actions


def repair_plan(checks: list[dict[str, Any]]) -> dict[str, Any]:
    actions = repair_actions(checks)
    return {
        "status": "ready" if not actions else "repair_needed",
        "actions": [action.to_dict() for action in actions],
        "automatic_actions": [action.id for action in actions if action.automatic],
        "manual_actions": [action.id for action in actions if not action.automatic],
    }
