"""v0.5: real render + QA e2e on synthetic media. Exercises the actual ffmpeg render stack and
the deterministic QA gates (incl. the v0.5 silencedetect routing fix) end-to-end, and proves the
source is never mutated. Gated behind needs_ffmpeg; marked slow (real encode)."""

import pytest

from eddy.config import RenderConfig, load_config
from eddy.edit.schema import Edl, EdlRange
from eddy.media.probe import stream_summary
from eddy.qa.deterministic import run_deterministic
from eddy.render.segments import render_edl
from eddy.runs import sha256_file


@pytest.mark.needs_ffmpeg
@pytest.mark.slow
def test_render_then_qa_e2e_and_source_unmutated(tmp_path, tiny_camera):
    before = sha256_file(tiny_camera)
    edl = Edl(
        sources={"camera": str(tiny_camera)},
        ranges=[EdlRange(source="camera", start=0.1, end=1.8)],
        total_duration_s=1.7,
    )
    out = tmp_path / "final" / "video.mp4"
    out.parent.mkdir(parents=True)

    render_edl(edl, out, tmp_path, RenderConfig())

    # a real, playable video came out
    s = stream_summary(out)
    assert s["video"] is not None and s["audio"] is not None
    assert 1.3 < s["duration_s"] < 2.1

    # the deterministic QA gates run for real on the rendered output and pass
    cfg = load_config()
    qa = run_deterministic(out, edl, tmp_path, cfg)
    assert qa["pass"], [g for g in qa["gates"] if not g["pass"]]

    # the source footage is byte-for-byte untouched
    assert sha256_file(tiny_camera) == before
