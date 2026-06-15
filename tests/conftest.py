"""Shared test fixtures + markers.

Synthetic media is generated on the fly with ffmpeg lavfi (no committed binaries) and gated behind
the `needs_ffmpeg` marker, so the pure-logic suite still runs on a machine without ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_ffmpeg: requires the ffmpeg binary (synthetic media)")
    config.addinivalue_line("markers", "e2e: full-pipeline end-to-end test")
    config.addinivalue_line("markers", "slow: slow test (real render / model)")


@pytest.fixture(scope="session")
def ffmpeg_required():
    if not _HAS_FFMPEG:
        pytest.skip("ffmpeg not installed")


def _lavfi(path: Path, *, seconds: float = 2.0, size: str = "320x240", rate: int = 30,
           audio: bool = True, source: str = "testsrc") -> Path:
    src = (f"{source}=size={size}:rate={rate}:duration={seconds}" if source != "color"
           else f"color=c=black:size={size}:rate={rate}:duration={seconds}")
    args = ["ffmpeg", "-y", "-f", "lavfi", "-i", src]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    args += ["-shortest", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(args, capture_output=True, check=True)
    return path


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("media-fixtures")


@pytest.fixture(scope="session")
def tiny_camera(fixtures_dir, ffmpeg_required):
    """A 2s 320x240 clip with a 440Hz tone (video + audio)."""
    return _lavfi(fixtures_dir / "camera.mp4")


@pytest.fixture(scope="session")
def tiny_silent(fixtures_dir, ffmpeg_required):
    """A 2s clip with NO audio stream."""
    return _lavfi(fixtures_dir / "silent.mp4", audio=False)


@pytest.fixture(scope="session")
def tiny_vertical(fixtures_dir, ffmpeg_required):
    """A vertical (portrait) clip."""
    return _lavfi(fixtures_dir / "vertical.mp4", size="240x426")


@pytest.fixture(scope="session")
def tiny_webm(fixtures_dir, ffmpeg_required):
    return _lavfi(fixtures_dir / "clip.webm")


@pytest.fixture(scope="session")
def corrupt_video(fixtures_dir):
    """Garbage bytes with a video extension — ffprobe must fail to decode this."""
    p = fixtures_dir / "corrupt.mp4"
    p.write_bytes(b"not a real video" * 64)
    return p
