"""v1.0: small pure-logic coverage for the long-render iteration resolver."""

import pytest

from eddy.config import RenderConfig
from eddy.render.long import latest_iteration_dir
from eddy.render import segments
from eddy.render.segments import _concat_segments_filtergraph, _segment_args, _segment_args_dual


def test_latest_iteration_dir_picks_highest(tmp_path):
    for n in ("01", "02", "10"):
        (tmp_path / "iterations" / n).mkdir(parents=True)
    assert latest_iteration_dir(tmp_path).name == "10"  # numeric-padded sort, highest last


def test_latest_iteration_dir_raises_when_none(tmp_path):
    (tmp_path / "iterations").mkdir()
    with pytest.raises(FileNotFoundError, match="run `eddy plan` first"):
        latest_iteration_dir(tmp_path)


def test_single_segment_args_filter_trim_preroll_without_output_seek(tmp_path):
    args = _segment_args(
        tmp_path / "camera.mp4",
        tmp_path / "out.mp4",
        start=3.0,
        end=5.0,
        fade_s=0.03,
        proxy_height=480,
        proxy_preset="veryfast",
    )
    vf = args[args.index("-vf") + 1]
    af = args[args.index("-af") + 1]
    assert "trim=start=2.000:duration=2.000" in vf
    assert "atrim=start=2.000:duration=2.000" in af
    assert args.count("-ss") == 1
    assert "-pix_fmt" in args and "yuv420p" in args


def test_dual_segment_args_puts_camera_bottom_right_and_trims_after_preroll(tmp_path):
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
    assert "trim=start=2.000:duration=2.000" in graph
    assert "atrim=start=2.000:duration=2.000" in graph
    assert args.count("-ss") == 2
    assert args.index(str(tmp_path / "mask.png")) > args.index(str(tmp_path / "camera.mp4"))


def test_long_concat_uses_filtergraph_reencode(monkeypatch, tmp_path):
    seen = {}

    def fake_run_ffmpeg(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs

    monkeypatch.setattr(segments, "run_ffmpeg", fake_run_ffmpeg)
    paths = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
    result = _concat_segments_filtergraph(paths, tmp_path / "out.mp4", tmp_path, RenderConfig(), proxy=True)

    argv = seen["argv"]
    assert result["strategy"] == "filtergraph_reencode_concat"
    assert "-filter_complex" in argv
    graph = argv[argv.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=1" in graph
    assert graph.count("setsar=1") == 2
    assert "-f" not in argv[:4]
    assert result["concat_demuxer_copy"] is False
