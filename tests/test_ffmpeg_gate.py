"""v0.4: ffmpeg concat quoting (apostrophe paths) + the never-write-outside-run-dir hard gate."""

import pytest

from eddy.media.ffmpeg import FfmpegError, _assert_outputs_inside, concat_quote


# --- concat_quote: ffmpeg concat-demuxer escaping, not shell ------------------------

def test_concat_quote_plain_path():
    assert concat_quote("/runs/a/0001.mp4") == "'/runs/a/0001.mp4'"


def test_concat_quote_escapes_apostrophe():
    # the bug: shlex.quote produced shell escaping the concat demuxer can't parse, so any
    # path with an apostrophe hard-failed the render. ffmpeg wants a literal ' written '\''.
    assert concat_quote("/v/it's a.mp4") == "'/v/it'\\''s a.mp4'"


def test_concat_quote_wraps_and_balances_quotes():
    q = concat_quote("/x/o'clock/'weird'.mp4")
    assert q.startswith("'") and q.endswith("'")


# --- _assert_outputs_inside: is_relative_to over every output -----------------------

def _argv(*paths_after_input, input_path="/external/source.mp4"):
    return ["-i", input_path, "-map", "0:v:0", *paths_after_input]


def test_output_inside_root_ok(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    _assert_outputs_inside(_argv(str(root / "final" / "video.mp4")), root)  # no raise


def test_output_outside_root_raises(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    with pytest.raises(FfmpegError, match="outside run dir"):
        _assert_outputs_inside(_argv("/tmp/evil.mp4"), root)


def test_sibling_prefix_does_not_bypass(tmp_path):
    # the startswith bug: "/runs/abc/x.mp4".startswith("/runs/ab") is True. is_relative_to closes it.
    (tmp_path / "runs" / "ab").mkdir(parents=True)
    (tmp_path / "runs" / "abc").mkdir(parents=True)
    root = tmp_path / "runs" / "ab"
    with pytest.raises(FfmpegError, match="outside run dir"):
        _assert_outputs_inside(_argv(str(tmp_path / "runs" / "abc" / "x.mp4")), root)


def test_input_outside_root_is_allowed(tmp_path):
    # source footage legitimately lives outside the run dir; only outputs are gated
    root = tmp_path / "run"
    root.mkdir()
    _assert_outputs_inside(
        ["-i", "/some/where/camera.mp4", str(root / "proxy.mp4")], root
    )  # no raise


def test_every_output_checked_not_just_last(tmp_path):
    # a multi-output command must not bypass the gate by putting the bad write earlier
    root = tmp_path / "run"
    root.mkdir()
    argv = ["-i", "/ext/in.mp4", "/tmp/outside.mp4", "-map", "0:a", str(root / "ok.mp4")]
    with pytest.raises(FfmpegError, match="outside run dir"):
        _assert_outputs_inside(argv, root)
