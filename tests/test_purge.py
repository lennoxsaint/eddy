"""v0.7: GDPR/CCPA purge — remove PII (transcript, face frames, caption text); --full erases all."""

import pytest

from eddy.clean import purge_run
from eddy.runs import SourceError


def _seed(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text("{}")  # makes it look like a real run (for --full guard)
    (run_dir / "transcript").mkdir(parents=True)
    (run_dir / "transcript" / "words.json").write_text('{"x":1}')
    (run_dir / "transcript" / "audio-16k.wav").write_bytes(b"audio" * 100)
    final = run_dir / "final"
    final.mkdir()
    (final / "video.mp4").write_bytes(b"keep" * 100)         # deliverable — kept on a PII purge
    (final / "transcript.md").write_text("the person's words")  # PII
    (final / "subtitles.srt").write_text("1\n00:00 --> 00:01\nwords")  # PII
    (final / "titles.md").write_text("keep")                  # deliverable
    refs = final / "thumbnails" / "refs"
    refs.mkdir(parents=True)
    (refs / "face-0.jpg").write_bytes(b"face" * 100)          # PII (face frame)


def test_purge_removes_pii_keeps_deliverables(tmp_path):
    _seed(tmp_path)
    info = purge_run(tmp_path, full=False)
    # PII gone
    assert not (tmp_path / "transcript").exists()
    assert not (tmp_path / "final" / "transcript.md").exists()
    assert not (tmp_path / "final" / "subtitles.srt").exists()
    assert not (tmp_path / "final" / "thumbnails" / "refs").exists()
    # deliverables kept
    assert (tmp_path / "final" / "video.mp4").exists()
    assert (tmp_path / "final" / "titles.md").exists()
    assert info["full"] is False and info["removed"]


def test_purge_dry_run_deletes_nothing(tmp_path):
    _seed(tmp_path)
    info = purge_run(tmp_path, dry_run=True)
    assert info["dry_run"] is True and info["removed"]
    assert (tmp_path / "transcript" / "words.json").exists()  # nothing deleted


def test_purge_full_erases_everything(tmp_path):
    run = tmp_path / "run"
    _seed(run)
    info = purge_run(run, full=True)
    assert not run.exists() and info["full"] is True


def test_purge_full_refuses_non_run_dir(tmp_path):
    notarun = tmp_path / "important-docs"
    notarun.mkdir()
    (notarun / "thesis.txt").write_text("do not delete")
    with pytest.raises(SourceError, match="doesn't look like an Eddy run"):
        purge_run(notarun, full=True)
    assert notarun.exists() and (notarun / "thesis.txt").exists()  # untouched
