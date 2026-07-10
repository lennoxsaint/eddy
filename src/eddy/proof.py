"""Artifact-truth helpers for Shorts proof and motion activity."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageOps


Range = tuple[float, float]


def screen_proof_share(proof_ranges: Iterable[Range], short_ranges: Iterable[Range]) -> float:
    proof = _merge(proof_ranges)
    short = _merge(short_ranges)
    total = sum(end - start for start, end in short)
    if total <= 0:
        return 0.0
    covered = 0.0
    for proof_start, proof_end in proof:
        for short_start, short_end in short:
            covered += max(0.0, min(proof_end, short_end) - max(proof_start, short_start))
    return round(min(1.0, covered / total), 6)


def motion_activity_verdict(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [
        str(row.get("id", "unknown"))
        for row in rows
        if int(row.get("unique_states", 0)) < 3 or float(row.get("freeze_ratio", 1.0)) >= 0.8
    ]
    return {"pass": len(rows) >= 2 and not failed, "failed_beats": failed, "beats": rows}


def measure_motion_activity(media: Path, beats: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for beat in beats:
        beat_id = str(beat.get("id", "unknown"))
        try:
            start = float(beat["start"])
            duration = float(beat["dur"])
        except (KeyError, TypeError, ValueError):
            rows.append({"id": beat_id, "unique_states": 0, "freeze_ratio": 1.0})
            continue
        frames = _sample_gray_frames(media, start=start, duration=duration, fps=10)
        hashes = [_difference_hash(frame) for frame in frames]
        frozen = sum(left == right for left, right in zip(hashes, hashes[1:], strict=False))
        rows.append(
            {
                "id": beat_id,
                "unique_states": len(set(hashes)),
                "freeze_ratio": round(frozen / max(1, len(hashes) - 1), 4),
                "sampled_frames": len(hashes),
            }
        )
    return motion_activity_verdict(rows)


def screen_proof_verdict(
    final: Path,
    screen_source: Path,
    segment_receipt: Path,
    proof_ranges: Iterable[Range],
    *,
    excluded_final_ranges: Iterable[Range] = (),
    threshold: float = 0.75,
) -> dict[str, Any]:
    segments = [tuple(item) for item in json.loads(segment_receipt.read_text()).get("segments", [])]
    proof = tuple(proof_ranges)
    share = screen_proof_share(proof, segments)
    candidates = _mapped_proof_points(proof, segments, excluded_final_ranges)
    samples = _evenly_spaced(candidates, count=3)
    scores: list[dict[str, float]] = []
    for source_time, final_time in samples:
        actual_frame = _frame(final, final_time)
        source_frame = _frame(screen_source, source_time)
        if actual_frame is None or source_frame is None:
            continue
        actual = actual_frame.crop((0, 1230, 1080, 1838)).convert("L")
        expected = ImageOps.fit(source_frame.convert("RGB"), (1080, 608)).convert("L")
        actual = actual.crop((40, 40, 1040, 568))
        expected = expected.crop((40, 40, 1040, 568))
        scores.append(
            {
                "source_s": round(source_time, 3),
                "final_s": round(final_time, 3),
                "ssim": round(_global_ssim(actual, expected), 4),
            }
        )
    passed = share >= 0.25 and len(scores) >= 3 and all(row["ssim"] >= threshold for row in scores)
    return {
        "pass": passed,
        "screen_share": share,
        "threshold": threshold,
        "samples": scores,
        "reason": None if passed else "screen_proof_source_mismatch",
    }


def _merge(ranges: Iterable[Range]) -> list[Range]:
    merged: list[list[float]] = []
    for start, end in sorted((float(start), float(end)) for start, end in ranges):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _sample_gray_frames(
    media: Path,
    *,
    start: float,
    duration: float,
    fps: int,
) -> list[npt.NDArray[np.uint8]]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(media),
            "-vf",
            f"fps={fps},scale=32:32,format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    frame_size = 32 * 32
    return [
        np.frombuffer(result.stdout[offset : offset + frame_size], dtype=np.uint8).reshape((32, 32))
        for offset in range(0, len(result.stdout) - frame_size + 1, frame_size)
    ]


def _difference_hash(frame: npt.NDArray[np.uint8]) -> bytes:
    horizontal = frame[:, 1:] > frame[:, :-1]
    return np.packbits(horizontal).tobytes()


def _mapped_proof_points(
    proof_ranges: Iterable[Range],
    segments: list[Range],
    excluded_final_ranges: Iterable[Range],
) -> list[tuple[float, float]]:
    excluded = _merge(excluded_final_ranges)
    points: list[tuple[float, float]] = []
    final_cursor = 0.0
    for segment_start, segment_end in segments:
        for proof_start, proof_end in proof_ranges:
            start = max(segment_start, proof_start)
            end = min(segment_end, proof_end)
            if end <= start:
                continue
            for fraction in (0.2, 0.5, 0.8):
                source_time = start + (end - start) * fraction
                final_time = final_cursor + (source_time - segment_start)
                if not any(a <= final_time <= b for a, b in excluded):
                    points.append((source_time, final_time))
        final_cursor += segment_end - segment_start
    return points


def _evenly_spaced(values: list[tuple[float, float]], *, count: int) -> list[tuple[float, float]]:
    if len(values) <= count:
        return values
    indexes = np.linspace(0, len(values) - 1, count).round().astype(int)
    return [values[index] for index in indexes]


def _frame(media: Path, timestamp: float) -> Image.Image | None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(media),
            "-frames:v",
            "1",
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
    from io import BytesIO

    return Image.open(BytesIO(result.stdout)).copy()


def _global_ssim(left: Image.Image, right: Image.Image) -> float:
    x = np.asarray(left, dtype=np.float64)
    y = np.asarray(right, dtype=np.float64)
    if x.shape != y.shape:
        return 0.0
    mean_x, mean_y = float(x.mean()), float(y.mean())
    var_x, var_y = float(x.var()), float(y.var())
    covariance = float(((x - mean_x) * (y - mean_y)).mean())
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    denominator = (mean_x**2 + mean_y**2 + c1) * (var_x + var_y + c2)
    if denominator == 0:
        return 1.0 if np.array_equal(x, y) else 0.0
    return float(((2 * mean_x * mean_y + c1) * (2 * covariance + c2)) / denominator)
