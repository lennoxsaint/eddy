"""v1.0: small pure-logic coverage for the long-render iteration resolver."""

import pytest

from eddy.config import RenderConfig
from eddy.render.long import latest_iteration_dir
from eddy.render.segments import _segment_args_dual


def test_latest_iteration_dir_picks_highest(tmp_path):
    for n in ("01", "02", "10"):
        (tmp_path / "iterations" / n).mkdir(parents=True)
    assert latest_iteration_dir(tmp_path).name == "10"  # numeric-padded sort, highest last


def test_latest_iteration_dir_raises_when_none(tmp_path):
    (tmp_path / "iterations").mkdir()
    with pytest.raises(FileNotFoundError, match="run `eddy plan` first"):
        latest_iteration_dir(tmp_path)


def test_dual_segment_args_puts_camera_bottom_right_and_mask_before_output_seek(tmp_path):
    cfg = RenderConfig(long_camera_size=260, long_camera_radius=100, long_camera_margin=0)
    args = _segment_args_dual(
        tmp_path / "camera.mp4",
        tmp_path / "screen.mp4",
        tmp_path / "mask.png",
        tmp_path / "out.mp4",
        start=3.0,
        end=5.0,
        fade_s=0.03,
        render_cfg=cfg,
        proxy_height=None,
        proxy_preset="veryfast",
    )
    graph = args[args.index("-filter_complex") + 1]
    assert "overlay=1660:820" in graph  # 1920x1080 canvas, 260px camera, zero margin
    assert args.index(str(tmp_path / "mask.png")) < args.index("-ss", args.index(str(tmp_path / "mask.png")))
