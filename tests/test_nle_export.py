"""v0.8: editor-native CMX3600 EDL export — a universal NLE timeline from the EDL ranges."""

from eddy.edit.schema import Edl, EdlRange
from eddy.package.nle_export import _tc, build_cmx3600, write_edl


def test_timecode_at_30fps():
    assert _tc(0.0, 30) == "00:00:00:00"
    assert _tc(1.0, 30) == "00:00:01:00"
    assert _tc(1.5, 30) == "00:00:01:15"   # 0.5s = 15 frames
    assert _tc(3661.0, 30) == "01:01:01:00"


def _edl():
    return Edl(
        sources={"camera": "/x/footage/talk.mp4"},
        ranges=[EdlRange(source="camera", start=2.0, end=5.0), EdlRange(source="camera", start=10.0, end=12.0)],
        total_duration_s=5.0,
    )


def test_build_cmx3600_structure():
    out = build_cmx3600(_edl(), fps=30, title="MY EDIT")
    assert out.startswith("TITLE: MY EDIT\nFCM: NON-DROP FRAME")
    lines = [ln for ln in out.splitlines() if ln and ln[0].isdigit()]
    assert len(lines) == 2  # two cut events
    # event 1: source in 00:00:02:00 -> out 00:00:05:00; record in 00:00:00:00 -> out 00:00:03:00
    assert "001" in lines[0] and "00:00:02:00 00:00:05:00 00:00:00:00 00:00:03:00" in lines[0]
    assert "C" in lines[0]
    # event 2 record-in continues from the first event's length (3s)
    assert "00:00:10:00 00:00:12:00 00:00:03:00 00:00:05:00" in lines[1]
    assert "* FROM CLIP NAME: talk.mp4" in out  # source basename, not the full path


def test_write_edl_creates_file(tmp_path):
    out = write_edl(_edl(), tmp_path, fps=30)
    assert out.name == "timeline.edl" and out.exists()
    assert "TITLE:" in out.read_text()
