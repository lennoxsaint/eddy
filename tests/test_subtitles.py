"""v0.7: sidecar SRT + VTT of the final cut (accessibility + SEO) from the output-timeline transcript."""

from eddy.render.subtitles import _ts, build_srt, build_vtt, write_subtitles

PHRASES = [
    {"out_start": 0.0, "out_end": 2.5, "text": "Systems beat goals."},
    {"out_start": 2.5, "out_end": 5.25, "text": "Here is why."},
    {"out_start": 5.25, "out_end": 5.25, "text": "zero-length dropped"},  # end<=start -> skipped
    {"out_start": 6.0, "out_end": 8.0, "text": "   "},                    # empty -> skipped
]


def test_ts_formats_srt_and_vtt():
    assert _ts(0.0, ",") == "00:00:00,000"
    assert _ts(3661.5, ",") == "01:01:01,500"
    assert _ts(2.5, ".") == "00:00:02.500"


def test_ts_rounding_spillover():
    assert _ts(1.9999, ",") == "00:00:02,000"  # ms rounds to 1000 -> next second


def test_build_srt_structure():
    srt = build_srt(PHRASES)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:02,500\nSystems beat goals.")
    assert "2\n00:00:02,500 --> 00:00:05,250\nHere is why." in srt
    assert "zero-length" not in srt and "dropped" not in srt  # invalid cues skipped


def test_build_vtt_has_header_and_dot_timestamps():
    vtt = build_vtt(PHRASES)
    assert vtt.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:02.500" in vtt
    assert "-->" in vtt and "," not in vtt.split("\n")[2]  # VTT uses '.' not ','


def test_write_subtitles_creates_both_files(tmp_path):
    info = write_subtitles(PHRASES, tmp_path, stem="subtitles")
    assert info["srt"].exists() and info["vtt"].exists()
    assert info["cues"] == 2  # two valid cues
    assert info["srt"].read_text().startswith("1\n")
    assert info["vtt"].read_text().startswith("WEBVTT")
