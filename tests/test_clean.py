"""v0.6: eddy clean reclaims scratch (segment dirs, proxies, 16k WAV) without touching deliverables."""

from eddy.clean import clean_run, dir_size_bytes


def _seed(run_dir):
    # deliverables (must survive)
    (run_dir / "final").mkdir(parents=True)
    (run_dir / "final" / "video.mp4").write_bytes(b"keep" * 100)
    (run_dir / "final" / "launch-kit").mkdir()
    (run_dir / "final" / "launch-kit" / "titles.md").write_text("keep")
    (run_dir / "manifest.json").write_text("{}")
    (run_dir / "receipts.jsonl").write_text("{}\n")
    it = run_dir / "iterations" / "01"
    it.mkdir(parents=True)
    (it / "edl.json").write_text("{}")  # audit trail — keep
    # scratch (must be pruned)
    (it / "proxy.mp4").write_bytes(b"scratch" * 500)
    segs = run_dir / "final" / "video_segments"
    segs.mkdir()
    (segs / "0000.mp4").write_bytes(b"seg" * 1000)
    (run_dir / "transcript").mkdir()
    (run_dir / "transcript" / "audio-16k.wav").write_bytes(b"wav" * 1000)
    (run_dir / "transcript" / "words.json").write_text("{}")  # keep


def test_clean_removes_scratch_keeps_deliverables(tmp_path):
    _seed(tmp_path)
    before = dir_size_bytes(tmp_path)
    info = clean_run(tmp_path, dry_run=False)

    # scratch gone
    assert not (tmp_path / "final" / "video_segments").exists()
    assert not (tmp_path / "iterations" / "01" / "proxy.mp4").exists()
    assert not (tmp_path / "transcript" / "audio-16k.wav").exists()
    # deliverables + audit trail kept
    assert (tmp_path / "final" / "video.mp4").exists()
    assert (tmp_path / "final" / "launch-kit" / "titles.md").exists()
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "iterations" / "01" / "edl.json").exists()
    assert (tmp_path / "transcript" / "words.json").exists()
    # reported real savings
    assert info["freed_mb"] >= 0 and dir_size_bytes(tmp_path) < before
    assert any("video_segments" in r for r in info["removed"])


def test_clean_dry_run_deletes_nothing(tmp_path):
    _seed(tmp_path)
    before = dir_size_bytes(tmp_path)
    info = clean_run(tmp_path, dry_run=True)
    assert info["dry_run"] is True
    assert info["removed"]  # it found scratch to report
    assert (tmp_path / "final" / "video_segments").exists()  # but deleted nothing
    assert dir_size_bytes(tmp_path) == before
