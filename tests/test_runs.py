"""Run lifecycle: source discovery + the read-only hash guard."""

import json

import pytest

from eddy.runs import SourceError, discover_sources, sha256_file, verify_sources_unmutated


def _vid(path, data=b"fake-video-bytes"):
    path.write_bytes(data)
    return path


def test_discover_single_file(tmp_path):
    v = _vid(tmp_path / "raw-video.mp4")
    assert discover_sources(v) == {"camera": v}


def test_discover_named_dir(tmp_path):
    cam = _vid(tmp_path / "camera.mp4")
    scr = _vid(tmp_path / "screen.mp4")
    mic = _vid(tmp_path / "mic.wav")
    found = discover_sources(tmp_path)
    assert found == {"camera": cam, "screen": scr, "mic": mic}


def test_discover_single_unnamed_video_in_dir(tmp_path):
    v = _vid(tmp_path / "whatever.mp4")
    assert discover_sources(tmp_path)["camera"] == v


def test_discover_ambiguous_videos_raises(tmp_path):
    _vid(tmp_path / "a.mp4")
    _vid(tmp_path / "b.mp4")
    with pytest.raises(SourceError, match="multiple videos"):
        discover_sources(tmp_path)


def test_discover_non_video_raises(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("x")
    with pytest.raises(SourceError):
        discover_sources(f)


def test_source_mutation_detected(tmp_path):
    src = _vid(tmp_path / "camera.mp4")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(
        json.dumps({"sources": {"camera": str(src)}, "source_sha256": {"camera": sha256_file(src)}})
    )
    assert verify_sources_unmutated(run_dir) == {"camera": True}
    src.write_bytes(b"MUTATED")
    with pytest.raises(SourceError, match="SOURCE MUTATED"):
        verify_sources_unmutated(run_dir)
