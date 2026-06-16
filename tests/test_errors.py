"""v0.5: friendly error mapping + crash log so failures are actionable, not raw tracebacks."""

from eddy.errors import friendly_by_name, friendly_error, write_crash_log
from eddy.loop.controller import EditLoopError
from eddy.media.ffmpeg import FfmpegError
from eddy.providers.base import ProviderError
from eddy.runs import SourceError


def test_source_error_is_input_problem():
    head, nxt = friendly_error(SourceError("no video files"))
    assert "Input problem" in head and "no video files" in head
    assert nxt  # a concrete next step


def test_ffmpeg_error_points_at_ffmpeg():
    head, nxt = friendly_error(FfmpegError("boom"))
    assert "Media error" in head and "ffmpeg" in nxt.lower()


def test_provider_error_points_at_doctor():
    head, nxt = friendly_error(ProviderError("brain down"))
    assert "brain" in head.lower() and "doctor" in nxt.lower()


def test_editloop_error_suggests_stronger_brain():
    head, nxt = friendly_error(EditLoopError("no compilable edl"))
    assert "shippable edit" in head.lower()


def test_unknown_error_is_generic_with_type():
    head, nxt = friendly_error(ValueError("weird"))
    assert "ValueError" in head and "crash log" in nxt.lower()


def test_friendly_by_name_maps_known_class_and_generic():
    # the string-only path the TUI uses when it reconstructs a failure from a log/receipt
    head, nxt = friendly_by_name("SourceError", "no video files")
    assert "Input problem" in head and "no video files" in head and nxt
    head, nxt = friendly_by_name("KaboomError", "weird")
    assert "Unexpected KaboomError" in head and "crash log" in nxt.lower()


def test_write_crash_log_captures_traceback(tmp_path):
    try:
        raise FfmpegError("kaboom")
    except FfmpegError as e:
        log = write_crash_log(e, run_dir=tmp_path)
    assert log.exists()
    body = log.read_text()
    assert "FfmpegError" in body and "kaboom" in body
    assert "eddy" in body and "platform:" in body
