"""v0.4: segments render to a .partial then atomically rename, so an interrupted render never
leaves a truncated segment that --resume would reuse."""

from pathlib import Path

from eddy.config import RenderConfig
from eddy.edit.schema import Edl, EdlRange
from eddy.render import segments


def test_segments_render_via_partial_then_rename(tmp_path, monkeypatch):
    def fake_ffmpeg(args, run_dir=None, receipts=None, timeout=3600):
        Path(args[-1]).write_bytes(b"x" * 2048)  # ffmpeg writes the last-arg output path

        class _P:
            returncode = 0

        return _P()

    monkeypatch.setattr(segments, "run_ffmpeg", fake_ffmpeg)
    edl = Edl(
        sources={"camera": "/x/cam.mp4"},
        ranges=[EdlRange(start=0, end=1), EdlRange(start=2, end=3)],
        total_duration_s=2,
    )
    out = tmp_path / "video.mp4"
    segments.render_edl(edl, out, tmp_path, RenderConfig())

    seg_dir = out.parent / (out.stem + "_segments")
    assert len(list(seg_dir.glob("0000_*.mp4"))) == 1
    assert len(list(seg_dir.glob("0001_*.mp4"))) == 1
    assert not list(seg_dir.glob("*.partial*"))  # no truncated leftovers from the rename flow
    assert out.exists()
