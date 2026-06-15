"""Pure parsing/packing logic in eddy.transcribe.pack.

Two surfaces under test:
- detect_audio_silence: parses ffmpeg silencedetect stderr into [{start,end,dur}]
  spans (subprocess mocked — we feed synthetic stderr text).
- pack_run: packs word-level transcript into phrase lines + a gap/silence map.
"""

import json

from eddy.transcribe import pack


class _FakeProc:
    def __init__(self, stderr):
        self.stderr = stderr


def _mock_ffmpeg(monkeypatch, stderr):
    """Make pack.detect_audio_silence return our synthetic ffmpeg stderr."""
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd
        return _FakeProc(stderr)

    monkeypatch.setattr(pack.subprocess, "run", fake_run)
    return calls


def _write_words(run_dir, words):
    tdir = run_dir / "transcript"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "words.json").write_text(json.dumps({"segments": [{"words": words}]}))
    return tdir


# --------------------------------------------------------------------------- #
# detect_audio_silence — silencedetect stderr parsing
# --------------------------------------------------------------------------- #


def test_parses_paired_start_end_spans(monkeypatch):
    stderr = (
        "[silencedetect @ 0x1] silence_start: 1.234\n"
        "[silencedetect @ 0x1] silence_end: 2.5 | silence_duration: 1.266\n"
        "[silencedetect @ 0x1] silence_start: 9.0\n"
        "[silencedetect @ 0x1] silence_end: 12.0 | silence_duration: 3.0\n"
    )
    _mock_ffmpeg(monkeypatch, stderr)
    spans = pack.detect_audio_silence("/x.wav")
    assert spans == [
        {"start": 1.234, "end": 2.5, "dur": 1.266},
        {"start": 9.0, "end": 12.0, "dur": 3.0},
    ]


def test_span_running_to_eof_is_captured(monkeypatch):
    # When silence runs to the end of the file, ffmpeg still emits a closing
    # silence_end at the file's total duration — that final span must survive.
    stderr = (
        "silence_start: 0.5\n"
        "silence_end: 1.2 | silence_duration: 0.7\n"
        "silence_start: 7.8\n"
        "silence_end: 10.0 | silence_duration: 2.2\n"  # 10.0 == EOF
    )
    _mock_ffmpeg(monkeypatch, stderr)
    spans = pack.detect_audio_silence("/x.wav")
    assert spans[-1] == {"start": 7.8, "end": 10.0, "dur": 2.2}
    assert len(spans) == 2


def test_dangling_silence_start_without_end_is_dropped(monkeypatch):
    # A silence_start with no matching silence_end never becomes a span.
    stderr = (
        "silence_start: 1.0\n"
        "silence_end: 2.0 | silence_duration: 1.0\n"
        "silence_start: 5.0\n"  # no closing end -> incomplete -> dropped
    )
    _mock_ffmpeg(monkeypatch, stderr)
    spans = pack.detect_audio_silence("/x.wav")
    assert spans == [{"start": 1.0, "end": 2.0, "dur": 1.0}]


def test_negative_start_is_clamped_to_zero(monkeypatch):
    # ffmpeg can report a slightly-negative silence_start near t=0.
    stderr = "silence_start: -0.004\nsilence_end: 0.5 | silence_duration: 0.504\n"
    _mock_ffmpeg(monkeypatch, stderr)
    spans = pack.detect_audio_silence("/x.wav")
    assert spans == [{"start": 0.0, "end": 0.5, "dur": 0.504}]


def test_zero_or_negative_width_span_is_dropped(monkeypatch):
    # end must be strictly greater than start.
    stderr = "silence_start: 3.0\nsilence_end: 3.0 | silence_duration: 0.0\n"
    _mock_ffmpeg(monkeypatch, stderr)
    assert pack.detect_audio_silence("/x.wav") == []


def test_noise_and_duration_params_flow_into_filter(monkeypatch):
    calls = _mock_ffmpeg(monkeypatch, "")
    pack.detect_audio_silence("/some/audio.wav", noise_db=-28.0, min_d=0.6)
    cmd = calls["cmd"]
    # the silencedetect filter string carries the requested thresholds
    af = cmd[cmd.index("-af") + 1]
    assert af == "silencedetect=noise=-28.0dB:d=0.6"
    assert "/some/audio.wav" in cmd


def test_empty_stderr_yields_no_spans(monkeypatch):
    _mock_ffmpeg(monkeypatch, "")
    assert pack.detect_audio_silence("/x.wav") == []


# --------------------------------------------------------------------------- #
# pack_run — word -> phrase packing + gap recording
# --------------------------------------------------------------------------- #


def test_phrases_break_on_long_silence(tmp_path):
    # gap of 0.6s (>= 0.5 PHRASE_BREAK_S) splits into two phrases;
    # a 0.1s gap stays inside one phrase.
    words = [
        {"start": 0.0, "end": 0.4, "word": " Hello"},
        {"start": 0.45, "end": 0.8, "word": " world"},
        {"start": 1.4, "end": 1.7, "word": " foo"},   # gap 0.6 -> break
        {"start": 1.8, "end": 2.1, "word": " bar"},    # gap 0.1 -> same phrase
    ]
    _write_words(tmp_path, words)
    pack.pack_run(tmp_path)

    phrases = json.loads((tmp_path / "transcript" / "phrases.json").read_text())
    assert [p["text"] for p in phrases] == ["Hello world", "foo bar"]
    assert phrases[0] == {"start": 0.0, "end": 0.8, "text": "Hello world"}
    assert phrases[1] == {"start": 1.4, "end": 2.1, "text": "foo bar"}


def test_takes_packed_md_format(tmp_path):
    words = [
        {"start": 0.0, "end": 0.5, "word": " one"},
        {"start": 1.3, "end": 1.9, "word": " two"},  # gap 0.8 -> break
    ]
    _write_words(tmp_path, words)
    out = pack.pack_run(tmp_path)

    assert out.name == "takes_packed.md"
    text = out.read_text()
    assert text == "[0.00-0.50] one\n[1.30-1.90] two\n"


def test_gap_recorded_when_below_break_threshold(tmp_path):
    # 0.4s gap is >= GAP_RECORD_S (0.35) but < PHRASE_BREAK_S (0.5):
    # it must be recorded in silence-map but NOT split the phrase.
    words = [
        {"start": 0.0, "end": 0.4, "word": " foo"},
        {"start": 0.8, "end": 1.1, "word": " bar"},  # gap 0.4
        {"start": 1.15, "end": 1.4, "word": " baz"},  # gap 0.05 -> ignored
    ]
    _write_words(tmp_path, words)
    pack.pack_run(tmp_path)

    phrases = json.loads((tmp_path / "transcript" / "phrases.json").read_text())
    assert [p["text"] for p in phrases] == ["foo bar baz"]

    gaps = json.loads((tmp_path / "transcript" / "silence-map.json").read_text())
    assert gaps == [
        {"after_s": 0.4, "gap_s": 0.4, "before_word": "foo", "next_word": "bar"},
    ]


def test_small_gaps_record_nothing(tmp_path):
    # Every inter-word gap below GAP_RECORD_S -> empty silence map, one phrase.
    words = [
        {"start": 0.0, "end": 0.3, "word": " a"},
        {"start": 0.4, "end": 0.7, "word": " b"},
        {"start": 0.8, "end": 1.1, "word": " c"},
    ]
    _write_words(tmp_path, words)
    pack.pack_run(tmp_path)

    assert json.loads((tmp_path / "transcript" / "silence-map.json").read_text()) == []
    phrases = json.loads((tmp_path / "transcript" / "phrases.json").read_text())
    assert [p["text"] for p in phrases] == ["a b c"]


def test_audio_silence_map_roundtrip_and_missing(tmp_path):
    # missing audio-16k.wav -> build writes [] and reader returns [].
    (tmp_path / "transcript").mkdir()
    out = pack.build_audio_silence_map(tmp_path)
    assert out.name == "audio-silence.json"
    assert json.loads(out.read_text()) == []
    assert pack.audio_silence_map(tmp_path) == []

    # reader reflects whatever is cached on disk
    out.write_text(json.dumps([{"start": 1.0, "end": 2.0, "dur": 1.0}]))
    assert pack.audio_silence_map(tmp_path) == [{"start": 1.0, "end": 2.0, "dur": 1.0}]
