"""Pure parsers behind `eddy doctor` hardware/ffmpeg detection.

The detection flow itself shells out and is hard to unit-test, but the string parsers it relies on
are pure and easy to pin — and a wrong ffmpeg-version parse silently degrades the preflight gate.
"""

from __future__ import annotations

import pytest

from eddy.doctor import _ffmpeg_major, _linux_chip, _linux_ram_gb


@pytest.mark.parametrize(
    "line,expected",
    [
        ("ffmpeg version 8.0 Copyright (c) 2000-2024", 8),
        ("ffmpeg version n6.1.1 Copyright", 6),
        ("ffmpeg version 7.0.2-static https://...", 7),
        ("ffmpeg version 10.1", 10),
    ],
)
def test_ffmpeg_major_parses_known_banners(line, expected):
    assert _ffmpeg_major(line) == expected


def test_ffmpeg_major_returns_none_without_prefix():
    assert _ffmpeg_major("some unrelated output") is None
    assert _ffmpeg_major("") is None


def test_linux_ram_gb_rounds_kb_to_gib():
    # 16 GiB in kB.
    assert _linux_ram_gb("MemTotal:       16777216 kB\nMemFree: 100 kB") == 16


def test_linux_ram_gb_missing_or_malformed_is_none():
    assert _linux_ram_gb("SwapTotal: 0 kB") is None
    assert _linux_ram_gb("MemTotal: not-a-number kB") is None


def test_linux_chip_reads_model_name():
    cpuinfo = "processor\t: 0\nmodel name\t: AMD Ryzen 9 5900X 12-Core Processor\n"
    assert _linux_chip(cpuinfo) == "AMD Ryzen 9 5900X 12-Core Processor"


def test_linux_chip_unknown_when_absent():
    assert _linux_chip("processor\t: 0\n") == "unknown"
