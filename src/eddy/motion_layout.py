"""Environment-aware placement for compact motion panels."""

from __future__ import annotations

import copy
import subprocess
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import numpy.typing as npt
from PIL import Image


Frame = npt.NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class Box:
    name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


def extract_video_frame(
    media: Path,
    timestamp: float,
    *,
    width: int,
    height: int,
) -> Frame | None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{max(0.0, timestamp):.3f}",
            "-i",
            str(media),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:{height}",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return np.asarray(Image.open(BytesIO(result.stdout)).convert("RGB"), dtype=np.uint8).copy()


def resolve_motion_layout(
    brief: dict[str, Any],
    frames: Sequence[Frame | None],
    *,
    portrait: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Place every beat in the quietest valid region of its real background frame."""
    resolved = copy.deepcopy(brief)
    width = int(resolved.get("width", 1080 if portrait else 1920))
    height = int(resolved.get("height", 1920 if portrait else 1080))
    beats = resolved.get("beats", [])
    candidates = _candidate_boxes(width, height, portrait=portrait)
    reserved = _reserved_boxes(width, height, portrait=portrait)
    fallback = np.full((height, width, 3), 127, dtype=np.uint8)
    usage = {candidate.name: 0 for candidate in candidates}
    proof_rows: list[dict[str, Any]] = []

    for index, beat in enumerate(beats):
        frame = frames[index] if index < len(frames) else fallback
        if frame is None:
            frame = fallback
        if frame.shape[:2] != (height, width):
            frame = np.asarray(
                Image.fromarray(frame).resize((width, height), Image.Resampling.BILINEAR),
                dtype=np.uint8,
            )
        scored: list[tuple[float, Box, dict[str, float]]] = []
        for candidate in candidates:
            metrics = _background_metrics(frame, candidate)
            reserved_overlap = _reserved_overlap_ratio(candidate, reserved)
            score = (
                metrics["edge_density"]
                + metrics["variance"] * 0.35
                + reserved_overlap * 10.0
                + usage[candidate.name] * 0.025
            )
            scored.append((score, candidate, metrics))
        _, selected, metrics = min(scored, key=lambda item: item[0])
        usage[selected.name] += 1
        overlap = _reserved_overlap_ratio(selected, reserved)
        coverage = selected.width * selected.height / float(width * height)
        luminance = metrics["luminance"]
        theme = "light" if luminance >= 0.52 else "dark"
        beat.update(
            {
                "placement": selected.name,
                "x": selected.x,
                "y": selected.y,
                "w": selected.width,
                "h": selected.height,
                "theme": theme,
            }
        )
        row_pass = overlap <= 0.001 and coverage <= 0.12
        proof_rows.append(
            {
                "id": str(beat.get("id", f"beat-{index + 1}")),
                "start": float(beat.get("start", 0.0)),
                "dur": float(beat.get("dur", 1.0)),
                "placement": selected.name,
                "box": [selected.x, selected.y, selected.right, selected.bottom],
                "theme": theme,
                "background_luminance": round(luminance, 4),
                "background_edge_density": round(metrics["edge_density"], 4),
                "background_variance": round(metrics["variance"], 4),
                "frame_coverage_ratio": round(coverage, 4),
                "reserved_overlap_ratio": round(overlap, 6),
                "pass": row_pass,
            }
        )

    resolved["hud"] = "none"
    resolved["motion_contract"] = "contextual_skeuomorphic_v1"
    proof = {
        "contract": "contextual_skeuomorphic_v1",
        "portrait": portrait,
        "reserved_regions": [
            [box.x, box.y, box.right, box.bottom]
            for box in reserved
        ],
        "beats": proof_rows,
        "pass": len(proof_rows) == len(beats) and all(row["pass"] for row in proof_rows),
    }
    return resolved, proof


def _candidate_boxes(width: int, height: int, *, portrait: bool) -> tuple[Box, ...]:
    if portrait:
        box_width = round(width * 0.42)
        box_height = round(height * 0.24)
        y = round(height * 0.69)
        return (
            Box("lower-left", round(width * 0.055), y, box_width, box_height),
            Box("lower-right", round(width * 0.525), y, box_width, box_height),
            Box("lower-center", round(width * 0.29), y, box_width, box_height),
        )
    box_width = round(width * 0.31)
    box_height = round(height * 0.26)
    left = round(width * 0.04)
    right = width - left - box_width
    return (
        Box("top-left", left, round(height * 0.13), box_width, box_height),
        Box("top-right", right, round(height * 0.13), box_width, box_height),
        Box("middle-left", left, round(height * 0.39), box_width, box_height),
        Box("middle-right", right, round(height * 0.39), box_width, box_height),
        Box("bottom-left", left, round(height * 0.67), box_width, box_height),
    )


def _reserved_boxes(width: int, height: int, *, portrait: bool) -> tuple[Box, ...]:
    if portrait:
        return (
            Box("face", 0, 0, width, round(height * 0.59)),
            Box("captions", 0, round(height * 0.59), width, round(height * 0.08)),
            Box("footer", 0, round(height * 0.96), width, round(height * 0.04)),
        )
    return (
        Box(
            "camera-pip",
            round(width * 0.855),
            round(height * 0.72),
            round(width * 0.145),
            round(height * 0.28),
        ),
    )


def _background_metrics(frame: Frame, box: Box) -> dict[str, float]:
    crop = frame[box.y : box.bottom, box.x : box.right]
    if crop.size == 0:
        return {"luminance": 0.5, "edge_density": 1.0, "variance": 1.0}
    gray = (
        crop[..., 0].astype(np.float64) * 0.2126
        + crop[..., 1].astype(np.float64) * 0.7152
        + crop[..., 2].astype(np.float64) * 0.0722
    )
    horizontal = np.abs(np.diff(gray, axis=1))
    vertical = np.abs(np.diff(gray, axis=0))
    edge_pixels = np.count_nonzero(horizontal > 18.0) + np.count_nonzero(vertical > 18.0)
    edge_total = horizontal.size + vertical.size
    return {
        "luminance": float(np.mean(gray) / 255.0),
        "edge_density": float(edge_pixels / max(1, edge_total)),
        "variance": float(np.std(gray) / 255.0),
    }


def _reserved_overlap_ratio(box: Box, reserved: Sequence[Box]) -> float:
    area = float(box.width * box.height)
    overlap = 0.0
    for item in reserved:
        width = max(0, min(box.right, item.right) - max(box.x, item.x))
        height = max(0, min(box.bottom, item.bottom) - max(box.y, item.y))
        overlap += width * height
    return overlap / max(1.0, area)
