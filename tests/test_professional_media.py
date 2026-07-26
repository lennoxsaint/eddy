from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from eddy.pipeline import _grade_camera_footage, _mix_audio_plan


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_camera_grade_and_documented_audio_mix_survive_delivery(tmp_path: Path) -> None:
    media = tmp_path / "camera.mp4"
    music = tmp_path / "assets" / "audio" / "music.wav"
    click = tmp_path / "assets" / "audio" / "click.wav"
    music.parent.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30:duration=0.6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=48000:duration=0.6",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(media),
        ],
        check=True,
    )
    for path, frequency in ((music, 440), (click, 880)):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:sample_rate=48000:duration=0.2",
                str(path),
            ],
            check=True,
        )
    before = media.read_bytes()

    _grade_camera_footage(media)
    _mix_audio_plan(
        tmp_path,
        media,
        {
            "music": [
                {
                    "ref": "assets/audio/music.wav",
                    "mix_db": -30,
                }
            ],
            "sfx": [
                {
                    "ref": "assets/audio/click.wav",
                    "mix_db": -24,
                    "cue": "0.2",
                }
            ],
        },
    )

    assert media.is_file() and media.stat().st_size > 0
    assert media.read_bytes() != before
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(media),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert {"video", "audio"} <= set(probe.stdout.split())
