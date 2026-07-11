"""Artifact-truth helpers for Shorts proof and motion activity."""

from __future__ import annotations

import json
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageOps


Range = tuple[float, float]


def caption_terminal_punctuation_verdict(
    planned_words: list[dict[str, Any]],
    rendered_tokens: list[object],
) -> dict[str, Any]:
    """Prove the generated caption tokens preserve source sentence endings."""
    planned_tokens = [str(item.get("word", "")).strip() for item in planned_words]
    rendered = [str(item).strip() for item in rendered_tokens]
    mismatches: list[dict[str, object]] = []
    if len(planned_tokens) != len(rendered):
        return {
            "pass": False,
            "reason": "caption_token_count_changed",
            "expected_tokens": len(planned_tokens),
            "rendered_tokens": len(rendered),
            "mismatches": [],
        }
    expected_count = 0
    for index, (planned, actual) in enumerate(zip(planned_tokens, rendered, strict=True)):
        expected = _terminal_punctuation(planned)
        if not expected:
            continue
        expected_count += 1
        got = _terminal_punctuation(actual)
        if got != expected:
            mismatches.append(
                {"index": index, "expected": expected, "rendered": got, "word": planned}
            )
    return {
        "pass": not mismatches,
        "reason": None if not mismatches else "caption_terminal_punctuation_missing",
        "expected_terminal_marks": expected_count,
        "mismatches": mismatches,
    }


def caption_sync_verdict(
    planned_words: list[dict[str, Any]],
    delivered_words: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare burned-caption timing with a fresh transcript of the delivered Short."""
    planned_tokens = [_caption_token(item.get("word", "")) for item in planned_words]
    delivered_tokens = [_caption_token(item.get("word", "")) for item in delivered_words]
    planned_indexes = [index for index, token in enumerate(planned_tokens) if token]
    delivered_indexes = [index for index, token in enumerate(delivered_tokens) if token]
    planned_clean = [planned_tokens[index] for index in planned_indexes]
    delivered_clean = [delivered_tokens[index] for index in delivered_indexes]
    matcher = SequenceMatcher(a=planned_clean, b=delivered_clean, autojunk=False)
    pairs: list[tuple[int, int]] = []
    for block in matcher.get_matching_blocks():
        pairs.extend(
            (planned_indexes[block.a + offset], delivered_indexes[block.b + offset])
            for offset in range(block.size)
        )
    ratio = len(pairs) / max(1, len(planned_clean), len(delivered_clean))
    onset_errors = [
        abs(float(planned_words[left]["start"]) - float(delivered_words[right]["start"]))
        for left, right in pairs
    ]
    median_error = float(np.median(onset_errors)) if onset_errors else float("inf")
    p95_error = float(np.percentile(onset_errors, 95)) if onset_errors else float("inf")
    planned_span = _word_span(planned_words)
    delivered_span = _word_span(delivered_words)
    duration_ratio = planned_span / delivered_span if delivered_span > 0 else 0.0
    cue_holds = _caption_cue_holds(planned_words, max_words=5)
    median_cue_hold = float(np.median(cue_holds)) if cue_holds else 0.0
    passed = (
        ratio >= 0.65
        and 0.85 <= duration_ratio <= 1.15
        and median_error <= 0.30
        and p95_error <= 0.65
        and median_cue_hold >= 0.55
    )
    return {
        "pass": passed,
        "reason": None if passed else "caption_timeline_out_of_sync",
        "matched_word_ratio": round(ratio, 4),
        "duration_ratio": round(duration_ratio, 4),
        "median_onset_error_s": None if not onset_errors else round(median_error, 4),
        "p95_onset_error_s": None if not onset_errors else round(p95_error, 4),
        "median_cue_hold_s": round(median_cue_hold, 4),
        "matched_words": len(pairs),
    }


def contextual_motion_verdict(
    overlay: Path,
    placement: dict[str, Any],
) -> dict[str, Any]:
    """Verify the rendered overlay pixels obey the contextual placement contract."""
    if placement.get("contract") != "contextual_skeuomorphic_v1" or not placement.get("pass"):
        return {
            "pass": False,
            "contract": "contextual_skeuomorphic_v1",
            "reason": "motion_placement_proof_invalid",
            "beats": [],
        }
    reserved = [tuple(int(value) for value in box) for box in placement.get("reserved_regions", [])]
    rows: list[dict[str, Any]] = []
    for beat in placement.get("beats", []):
        start = float(beat.get("start", 0.0))
        duration = float(beat.get("dur", 1.0))
        frame = _frame(overlay, start + duration * 0.5)
        if frame is None:
            rows.append(
                {
                    "id": beat.get("id", "unknown"),
                    "pass": False,
                    "reason": "motion_overlay_frame_missing",
                }
            )
            continue
        rgb = np.asarray(frame.convert("RGB"), dtype=np.uint8)
        mask = np.max(rgb, axis=2) > 24
        active_pixels = int(np.count_nonzero(mask))
        frame_pixels = mask.size
        coverage = active_pixels / max(1, frame_pixels)
        overlap_pixels = 0
        for left, top, right, bottom in reserved:
            overlap_pixels += int(np.count_nonzero(mask[top:bottom, left:right]))
        overlap_ratio = overlap_pixels / max(1, active_pixels)
        y_values, x_values = np.nonzero(mask)
        actual_box = (
            [int(x_values.min()), int(y_values.min()), int(x_values.max()) + 1, int(y_values.max()) + 1]
            if active_pixels
            else None
        )
        expected = [int(value) for value in beat.get("box", [])]
        contained = (
            actual_box is not None
            and len(expected) == 4
            and actual_box[0] >= expected[0] - 48
            and actual_box[1] >= expected[1] - 48
            and actual_box[2] <= expected[2] + 48
            and actual_box[3] <= expected[3] + 48
        )
        row_pass = 0.003 <= coverage <= 0.12 and overlap_ratio <= 0.001 and contained
        rows.append(
            {
                "id": beat.get("id", "unknown"),
                "rendered_box": actual_box,
                "rendered_coverage_ratio": round(coverage, 5),
                "rendered_reserved_overlap_ratio": round(overlap_ratio, 6),
                "contained_by_placement": contained,
                "pass": row_pass,
            }
        )
    return {
        "pass": bool(rows) and len(rows) == len(placement.get("beats", [])) and all(
            row["pass"] for row in rows
        ),
        "contract": "contextual_skeuomorphic_v1",
        "reason": None if rows and all(row["pass"] for row in rows) else "motion_pixels_overlap",
        "beats": rows,
        "placement": placement,
    }


def _caption_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _terminal_punctuation(value: str) -> str:
    match = re.search(r"[.?!]+$", value.strip())
    if not match:
        return ""
    raw = match.group(0)
    return raw[-1] if raw[-1] in "?!" else "."


def _word_span(words: list[dict[str, Any]]) -> float:
    if not words:
        return 0.0
    return max(0.0, float(words[-1]["end"]) - float(words[0]["start"]))


def _caption_cue_holds(words: list[dict[str, Any]], *, max_words: int) -> list[float]:
    cues: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        if current and (
            len(current) >= max_words
            or float(word["end"]) - float(current[0]["start"]) > 2.0
        ):
            cues.append(current)
            current = []
        current.append(word)
    if current:
        cues.append(current)
    holds: list[float] = []
    for index, cue in enumerate(cues):
        next_start = (
            float(cues[index + 1][0]["start"])
            if index + 1 < len(cues)
            else float(cue[-1]["end"])
        )
        holds.append(max(0.0, next_start - float(cue[0]["start"])))
    return holds


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
