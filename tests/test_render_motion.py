from __future__ import annotations

import json
from pathlib import Path

import pytest

from eddy.config import EddyConfig
from eddy.motion.frame_spec import write_hyperframes_cache
from eddy.render import motion


class _Receipts:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def log(self, event: str, **payload) -> None:
        self.events.append((event, payload))


def test_first_60_motion_missing_cache_blocks_with_receipt(tmp_path):
    cfg = EddyConfig()
    cfg.motion.cache_dir = str(tmp_path / "missing-cache")
    receipts = _Receipts()

    with pytest.raises(RuntimeError, match="hyperframes_cache_missing"):
        motion.apply_first_60_motion(tmp_path / "video.mp4", tmp_path, cfg, receipts=receipts)

    assert receipts.events[-1][0] == "first_60_motion"
    assert receipts.events[-1][1]["quality_gate_pass"] is False


def test_first_60_motion_writes_contract_and_preserves_audio_copy(monkeypatch, tmp_path):
    hf = tmp_path / "hyperframes"
    (hf / "skills" / "motion-graphics").mkdir(parents=True)
    (hf / "skills" / "motion-graphics" / "SKILL.md").write_text("motion")
    (hf / "registry" / "components" / "caption-highlight").mkdir(parents=True)
    (hf / "registry" / "components" / "caption-highlight" / "index.tsx").write_text("caption")
    cache = tmp_path / "cache"
    write_hyperframes_cache(hf, cache)

    video = tmp_path / "final" / "long" / "video.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video-before")
    cfg = EddyConfig()
    cfg.motion.cache_dir = str(cache)
    cfg.motion.first_60_seconds = 45.0
    seen: list[list[str]] = []

    def fake_run_ffmpeg(args, run_dir=None, receipts=None):
        argv = [str(arg) for arg in args]
        seen.append(argv)
        out = Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"rendered")

    monkeypatch.setattr(motion, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        motion,
        "run_ffprobe",
        lambda _args: json.dumps({"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}),
    )

    result = motion.apply_first_60_motion(video, tmp_path, cfg, receipts=_Receipts())

    composite_args = seen[-1]
    assert result["quality_gate_pass"] is True
    assert (video.parent / "motion" / "first-60" / "frame.md").exists()
    assert (video.parent / "motion" / "first-60" / "storyboard.html").exists()
    assert result["copied_assets_count"] >= 1
    assert composite_args[composite_args.index("-map") + 1] == "[v]"
    assert "0:a?" in composite_args
    assert composite_args[composite_args.index("-c:a") + 1] == "copy"
