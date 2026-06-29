"""v1.0: small pure-logic coverage for the long-render iteration resolver."""

import pytest

from eddy.config import RenderConfig
from eddy.edit.schema import Edl, EdlRange, EditDecisions, save
from eddy.render import long as render_long
from eddy.render.long import latest_iteration_dir
from eddy.render import segments
from eddy.render.segments import (
    _concat_segments_filtergraph,
    _segment_args,
    _segment_args_dual,
    _visual_insert_filtergraph,
)


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


def test_visual_insert_filtergraph_writes_timed_text_files(tmp_path):
    graph, count = _visual_insert_filtergraph(
        [
            {
                "out_start_s": 1.2,
                "out_end_s": 5.5,
                "text": "Local route: Ollama runs on your machine. Nothing leaves the laptop.",
            }
        ],
        tmp_path,
        proxy=True,
    )

    assert count == 1
    assert "drawbox" in graph
    assert "drawtext" in graph
    assert "between(t\\,1.200\\,5.500)" in graph
    assert (tmp_path / "visual-insert-00.txt").read_text().startswith("Local route: Ollama")


def test_render_run_passes_visual_insert_notes(monkeypatch, tmp_path):
    iter_dir = tmp_path / "iterations" / "01"
    iter_dir.mkdir(parents=True)
    edl = Edl(
        sources={"camera": str(tmp_path / "camera.mp4")},
        ranges=[EdlRange(start=0, end=2)],
        total_duration_s=2,
    )
    decisions = EditDecisions(
        visual_insert_notes=[
            {"out_start_s": 0.5, "out_end_s": 1.5, "text": "Codex Club: repo plus commands"}
        ]
    )
    save(edl, iter_dir / "edl.json")
    save(decisions, iter_dir / "edit-decisions.json")
    seen = {}

    def fake_render_edl(*args, **kwargs):
        seen["visual_insert_notes"] = kwargs["visual_insert_notes"]
        out = args[1]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("rendered")
        return out

    monkeypatch.setattr(render_long, "render_edl", fake_render_edl)
    monkeypatch.setattr(render_long, "boundary_contact_sheet", lambda *a, **k: tmp_path / "sheet.jpg")

    render_long.render_run(tmp_path, proxy=True, iteration=1)

    assert seen["visual_insert_notes"] == decisions.visual_insert_notes
