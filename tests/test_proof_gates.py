import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from eddy.proof import (
    _global_ssim,
    measure_motion_activity,
    motion_activity_verdict,
    screen_proof_share,
    screen_proof_verdict,
)


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protected_silence_is_never_exempt_above_point_eight_seconds() -> None:
    verify = _load_script("verify")

    kept, violations = verify.apply_protected_pause_ceiling(
        [[2.0, 7.7], [9.0, 9.5]], [[0.0, 10.0]], ceiling=0.8
    )

    assert kept == []
    assert violations == [[2.0, 7.7]]


def test_splice_tightens_protected_silence_above_point_eight_seconds() -> None:
    splice = _load_script("splice")

    gaps = splice.span_gaps(
        0.0,
        10.0,
        [{"word": "before", "start": 0.0, "end": 1.0},
         {"word": "after", "start": 7.0, "end": 8.0}],
        [[1.0, 7.0]],
        [[0.0, 10.0]],
        0.2,
    )

    assert gaps == [[1.0, 7.0], [8.0, 10.0]]


def test_splice_preserves_onset_preroll_and_never_removes_through_words() -> None:
    splice = _load_script("splice")
    words = [
        {"word": "before", "start": 0.0, "end": 0.1},
        {"word": "after", "start": 0.7, "end": 0.8},
    ]

    segments = splice.compute_segments(
        [[0.0, 0.8]],
        words,
        [],
        threshold=0.2,
        target=0.1,
        silences=[[0.1, 0.74]],
        max_gap=0.28,
    )

    assert segments == [[0.0, 0.14], [0.64, 0.8]]


def test_single_pass_audio_splice_keeps_only_requested_intervals(tmp_path: Path) -> None:
    splice = _load_script("splice")
    source = tmp_path / "source.wav"
    output = tmp_path / "edited.m4a"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            str(source),
        ],
        check=True,
    )

    filter_graph, output_label = splice.build_audio_filter(
        [[0.0, 1.0], [3.0, 4.0]],
        xfade=0.012,
    )

    assert "asegment=" in filter_graph
    assert "atrim=" not in filter_graph
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-filter_complex",
            filter_graph,
            "-map",
            output_label,
            "-c:a",
            "aac",
            str(output),
        ],
        check=True,
    )
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert duration == pytest.approx(2.0, abs=0.03)


def test_splice_localizes_source_segments_into_bounded_seek_window() -> None:
    splice = _load_script("splice")

    seek_start, seek_duration, localized = splice.localize_segments(
        [[2240.59, 2244.878], [4514.403, 4518.228]],
        seek_preroll=0.1,
    )

    assert seek_start == pytest.approx(2240.49)
    assert seek_duration == pytest.approx(2277.838)
    assert localized[0] == pytest.approx([0.1, 4.388])
    assert localized[1] == pytest.approx([2273.913, 2277.738])


def test_seeked_render_does_not_add_a_video_frame_at_every_cut(tmp_path: Path) -> None:
    splice = _load_script("splice")
    source = tmp_path / "source.mp4"
    output = tmp_path / "edited.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30:duration=5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=5",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )

    splice.render(source, [[1.0, 2.0], [3.0, 4.0]], output, 0.012)

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,duration",
            "-of",
            "json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    durations = {
        item["codec_type"]: float(item["duration"])
        for item in json.loads(probe.stdout)["streams"]
    }
    assert durations["video"] == pytest.approx(2.0, abs=1 / 30)
    assert abs(durations["video"] - durations["audio"]) <= 1 / 30


def test_irregular_cut_boundaries_do_not_accumulate_av_drift(tmp_path: Path) -> None:
    splice = _load_script("splice")
    source = tmp_path / "source.mp4"
    output = tmp_path / "edited.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30:duration=5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=5",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )
    segments = [[0.113 + index * 0.4, 0.251 + index * 0.4] for index in range(10)]

    splice.render(source, segments, output, 0.012)

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,duration",
            "-of",
            "json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    durations = {
        item["codec_type"]: float(item["duration"])
        for item in json.loads(probe.stdout)["streams"]
    }
    assert abs(durations["video"] - durations["audio"]) <= 2 / 30


def test_large_video_timeline_uses_flat_expression() -> None:
    splice = _load_script("splice")
    segments = [[index * 0.003, index * 0.003 + 0.0015] for index in range(329)]

    selector, timeline = splice.build_video_timeline(segments)

    assert selector.count("gte(") == 329
    assert timeline.count("gte(") == 328
    assert "if(" not in timeline
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=32x32:rate=1000:duration=1",
            "-vf",
            f"select='{selector}',setpts='{timeline}'",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ],
        check=True,
    )


def test_absurd_whisper_word_duration_cannot_hide_audio_truth_silence() -> None:
    splice = _load_script("splice")
    words = [
        {"word": "setup", "start": 1.0, "end": 4.5},
        {"word": "after", "start": 4.7, "end": 5.0},
    ]

    gaps = splice.span_gaps(
        0.0,
        5.0,
        words,
        [[1.4, 4.6]],
        [],
        0.2,
    )

    assert any(start <= 2.0 and end >= 4.5 for start, end in gaps)


def test_screen_proof_requires_one_quarter_of_the_short() -> None:
    assert screen_proof_share(((0.0, 2.5),), ((0.0, 10.0),)) == 0.25
    assert screen_proof_share(((0.0, 2.4),), ((0.0, 10.0),)) < 0.25


def test_static_motion_cannot_pass_two_animated_beat_contract() -> None:
    verdict = motion_activity_verdict(
        [
            {"id": "hook", "unique_states": 1, "freeze_ratio": 1.0},
            {"id": "proof", "unique_states": 4, "freeze_ratio": 0.4},
        ]
    )

    assert verdict["pass"] is False
    assert verdict["failed_beats"] == ["hook"]


def test_motion_sampler_proves_each_declared_beat_moves(monkeypatch, tmp_path: Path) -> None:
    frames = []
    for edge in (4, 10, 16, 22):
        frame = np.zeros((32, 32), dtype=np.uint8)
        frame[:, edge:] = 255
        frames.append(frame)
    monkeypatch.setattr("eddy.proof._sample_gray_frames", lambda *_args, **_kwargs: frames)

    verdict = measure_motion_activity(
        tmp_path / "overlay.mp4",
        [
            {"id": "hook", "start": 0.0, "dur": 1.0},
            {"id": "proof", "start": 3.0, "dur": 1.0},
        ],
    )

    assert verdict["pass"] is True
    assert [row["sampled_frames"] for row in verdict["beats"]] == [4, 4]


def test_screen_proof_similarity_separates_matching_and_unrelated_frames() -> None:
    base = Image.fromarray(np.tile(np.arange(64, dtype=np.uint8), (64, 1)))
    unrelated = Image.fromarray(np.flipud(np.tile(np.arange(64, dtype=np.uint8), (64, 1)).T))

    assert _global_ssim(base, base) == 1.0
    assert _global_ssim(base, unrelated) < 0.75


def test_delivered_screen_proof_matches_three_source_mapped_samples(
    monkeypatch,
    tmp_path: Path,
) -> None:
    receipt = tmp_path / "segments.json"
    receipt.write_text(json.dumps({"segments": [[10.0, 20.0]]}) + "\n")
    source = Image.fromarray(
        np.dstack(
            [
                np.tile(np.arange(1080, dtype=np.uint16) % 256, (608, 1)).astype(np.uint8),
                np.tile(np.arange(608, dtype=np.uint16)[:, None] % 256, (1, 1080)).astype(np.uint8),
                np.full((608, 1080), 120, dtype=np.uint8),
            ]
        )
    )
    delivered = Image.new("RGB", (1080, 1920), "black")
    delivered.paste(source, (0, 1230))
    final_path = tmp_path / "final.mp4"
    source_path = tmp_path / "screen.mp4"
    monkeypatch.setattr(
        "eddy.proof._frame",
        lambda media, _timestamp: delivered if media == final_path else source,
    )

    verdict = screen_proof_verdict(
        final_path,
        source_path,
        receipt,
        ((10.0, 20.0),),
    )

    assert verdict["pass"] is True
    assert len(verdict["samples"]) == 3


def test_delivered_editorial_truth_catches_repeat_and_reset_loop(tmp_path: Path) -> None:
    verify = _load_script("verify")
    words_path = tmp_path / "final-words.json"
    tokens = [
        "you", "point", "this", "exact", "same", "thing.",
        "Okay.", "So", "the", "fix...", "Okay.",
        "you", "point", "this", "exact", "same", "thing.",
    ]
    words_path.write_text(
        __import__("json").dumps(
            {
                "words": [
                    {"word": token, "start": index * 0.2, "end": index * 0.2 + 0.1}
                    for index, token in enumerate(tokens)
                ]
            }
        )
        + "\n"
    )

    issues = verify.delivered_editorial_issues(words_path)

    assert {item["kind"] for item in issues} >= {"repeat", "reset_loop", "false_start"}


def test_delivered_gap_gate_enforces_point_two_eight_ceiling() -> None:
    verify = _load_script("verify")
    words = [
        {"word": "one", "start": 0.0, "end": 0.1},
        {"word": "two", "start": 0.2, "end": 0.3},
        {"word": "three", "start": 0.7, "end": 0.8},
    ]

    verdict = verify.word_gap_verdict(words, [], hard_max=0.28)

    assert verdict["pass"] is False
    assert verdict["violations"] == [[0.3, 0.7]]


def test_delivered_av_drift_gate_compares_stream_durations() -> None:
    verify = _load_script("verify")
    info = {
        "streams": [
            {"codec_type": "video", "duration": "12.000"},
            {"codec_type": "audio", "duration": "11.850"},
        ]
    }

    assert verify.av_duration_drift(info) == pytest.approx(0.15)
