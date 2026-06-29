"""v0.8: standalone `eddy shorts <source>` — transcribe -> one decision pass -> render shorts only,
skipping the iterative edit loop and the long-form render. Orchestration is mocked at the stage
boundaries; this asserts the sequence and that the long edit_loop is NOT invoked."""

import pytest

import eddy.edit.cutplan as cutplan_mod
import eddy.loop._orchestration as ctrl
import eddy.render.shorts as shorts_mod
from eddy.edit.schema import ShortsCandidate
from eddy.runs import SourceError


def test_mine_shorts_runs_plan_then_shorts_no_long_loop(tmp_path, monkeypatch):
    run_dir = tmp_path / "2026-06-16-ep"
    run_dir.mkdir()
    iter_dir = run_dir / "iterations" / "01"
    iter_dir.mkdir(parents=True)
    calls: list[str] = []

    monkeypatch.setattr(ctrl, "open_run", lambda source, slug=None, resume=False: run_dir)
    monkeypatch.setattr(ctrl, "manifest", lambda rd: {"sources": {"camera": "/x/ep.mp4"}})
    monkeypatch.setattr(ctrl, "assert_sources_decodable", lambda s: calls.append("preflight"))
    monkeypatch.setattr(ctrl, "transcribe_run", lambda rd, language=None: calls.append("transcribe"))
    monkeypatch.setattr(ctrl, "verify_sources_unmutated", lambda rd: calls.append("verify"))
    monkeypatch.setattr(ctrl, "run_cost_summary", lambda receipts: {"total_usd": 0.0, "calls": 0})
    # the long loop must never run in the standalone path
    monkeypatch.setattr(ctrl, "edit_loop", lambda *a, **k: (_ for _ in ()).throw(AssertionError("edit_loop ran")))

    def fake_plan(rd):
        calls.append("plan")
        return iter_dir

    def fake_render(rd, iteration_dir=None):
        calls.append("shorts")
        assert iteration_dir == iter_dir  # shorts rendered from the plan's iteration
        return [{"path": "a.mp4"}, {"path": "b.mp4"}]

    monkeypatch.setattr(cutplan_mod, "plan_run", fake_plan)
    monkeypatch.setattr(shorts_mod, "render_shorts", fake_render)

    out = ctrl.mine_shorts(source="/x/ep.mp4")
    assert out == run_dir
    assert calls == ["preflight", "transcribe", "plan", "shorts", "verify"]


def test_render_shorts_rejects_audio_only_source(tmp_path, monkeypatch):
    """An audio-only / stream-less camera fails loud at the top, not with a None['width'] crash mid-render."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(shorts_mod, "manifest", lambda rd: {"sources": {"camera": "/x/podcast.m4a"}})
    monkeypatch.setattr(shorts_mod, "latest_iteration_dir", lambda rd: run_dir / "iterations" / "01")
    monkeypatch.setattr(shorts_mod, "load_decisions", lambda p: object())
    monkeypatch.setattr(shorts_mod, "words_flat", lambda rd: [])
    # a source whose video stream probed to None (audio-only or corrupt)
    monkeypatch.setattr(
        shorts_mod, "stream_summary",
        lambda p: {"video": None, "audio": {"codec": "aac"}, "duration_s": 12.0},
    )
    with pytest.raises(SourceError, match="no video stream"):
        shorts_mod.render_shorts(run_dir)


def test_render_shorts_rejects_declared_but_missing_screen_source(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    camera = tmp_path / "camera.mp4"
    camera.write_bytes(b"not-real-video")
    missing_screen = tmp_path / "screen.mp4"
    monkeypatch.setattr(
        shorts_mod,
        "manifest",
        lambda rd: {"sources": {"camera": str(camera), "screen": str(missing_screen)}},
    )
    monkeypatch.setattr(shorts_mod, "latest_iteration_dir", lambda rd: run_dir / "iterations" / "01")

    with pytest.raises(SourceError, match="screen source was declared but is missing"):
        shorts_mod.render_shorts(run_dir)


def test_select_short_candidates_filters_weak_hooks_with_playbook():
    records = [
        {
            "opening_3s_text": "Stop making this creator mistake",
            "hook_pattern": "mistake warning",
        }
    ]
    candidates = [
        ShortsCandidate(start_s=10, end_s=40, hook="and then I went over here"),
        ShortsCandidate(start_s=20, end_s=50, hook="Stop making this creator mistake"),
    ]

    selected = shorts_mod.select_short_candidates(candidates, count=5, playbook_records=records)

    assert [c.hook for c in selected] == ["Stop making this creator mistake"]


def test_short_attempt_queue_tries_playbook_winners_then_remaining_candidates():
    winner = ShortsCandidate(start_s=20, end_s=50, hook="Stop making this creator mistake")
    fallback = ShortsCandidate(start_s=10, end_s=40, hook="and then I went over here")

    queue = shorts_mod._short_attempt_queue([winner], [fallback, winner])

    assert queue == [winner, fallback]


def test_short_silence_threshold_uses_shorts_dead_air_standard():
    cfg = shorts_mod.load_config()
    cfg.gates.max_output_silence_s = 0.6
    cfg.shorts.max_silent_motion_s = 1.2

    assert shorts_mod._short_silence_threshold(cfg) == 1.2


def test_quarantine_rejected_short_moves_failed_candidate_out_of_production_folder(tmp_path):
    out_root = tmp_path / "shorts"
    final = out_root / "failed-hook.mp4"
    final.parent.mkdir()
    final.write_bytes(b"failed-render")
    stale = out_root / "_rejected" / final.name
    stale.parent.mkdir()
    stale.write_bytes(b"stale-render")

    rejected = shorts_mod._quarantine_rejected_short(final, out_root)

    assert rejected == stale
    assert rejected.read_bytes() == b"failed-render"
    assert not final.exists()


def test_mined_short_candidates_use_raw_transcript_when_host_omits_shorts(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    phrases = [
        {"start": 0.0, "end": 6.0, "text": "Here is how to duplicate Codex and run any model inside it"},
        {"start": 6.2, "end": 13.0, "text": "You copy the app route and change the model provider"},
        {"start": 13.3, "end": 22.0, "text": "That means you can test local models and subscription agents"},
    ]
    monkeypatch.setattr(shorts_mod, "load_phrases", lambda rd: phrases)

    mined = shorts_mod._mined_short_candidates(run_dir, min_s=10, max_s=59, limit=5)

    assert mined
    assert mined[0].start_s == 0.0
    assert mined[0].end_s >= 13.0
    assert "duplicate Codex" in mined[0].hook


def test_write_short_blocker_creates_ledger_and_receipt(tmp_path):
    out_root = tmp_path / "shorts"
    out_root.mkdir()
    seen = {}

    class Receipts:
        def log(self, event, **payload):
            seen["event"] = event
            seen["payload"] = payload

    ledger = shorts_mod._write_short_blocker(
        out_root,
        Receipts(),
        "no_standalone_short_candidates",
        "No standalone moments.",
        {"candidate_count": 0},
    )

    assert ledger[0]["status"] == "blocked"
    assert ledger[0]["blocker"] == "no_standalone_short_candidates"
    assert (out_root / "shorts-ledger.json").exists()
    assert seen["event"] == "shorts_blocked"


def test_sub_segments_keep_positive_boundary_handles():
    words = [
        {"start": 1.0, "end": 1.3, "word": "Stop"},
        {"start": 1.4, "end": 1.7, "word": "this"},
        {"start": 1.8, "end": 2.1, "word": "now."},
    ]

    start, end = shorts_mod.sub_segments(words)[0]

    assert words[0]["start"] - start > 0
    assert end - words[-1]["end"] > 0


def test_shorts_segment_join_uses_blinkless_reencode_not_concat_copy(tmp_path, monkeypatch):
    """Visible camera cuts must not be assembled with concat-copy segment MP4s."""
    seen: dict[str, list[str]] = {}

    def fake_run_ffmpeg(args, run_dir=None, receipts=None):
        seen["args"] = [str(a) for a in args]

    monkeypatch.setattr(shorts_mod, "run_ffmpeg", fake_run_ffmpeg)

    result = shorts_mod._concat_segments_blinkless(
        [tmp_path / "segment-000.mp4", tmp_path / "segment-001.mp4"],
        tmp_path / "base.mp4",
        tmp_path,
    )

    args = seen["args"]
    graph = args[args.index("-filter_complex") + 1]
    assert result["strategy"] == "filtergraph_reencode_concat"
    assert result["reencoded"] is True
    assert result["concat_demuxer_copy"] is False
    assert "concat=n=2:v=1:a=1" in graph
    assert "setpts=PTS-STARTPTS" in graph
    assert graph.count("setsar=1") == 2
    assert "asetpts=PTS-STARTPTS" in graph
    assert ["-c", "copy"] not in [args[i : i + 2] for i in range(len(args) - 1)]


def test_join_boundary_times_reports_output_timeline_joins():
    assert shorts_mod._join_boundary_times([(10.0, 12.5), (20.0, 21.0), (30.0, 33.25)]) == [2.5, 3.5]


def test_dual_short_segments_use_filter_trim_not_fast_seek(tmp_path, monkeypatch):
    """Fast input seeking can create black lead-in frames in the camera panel."""
    seen: dict[str, list[str]] = {}

    def fake_run_ffmpeg(args, run_dir=None, receipts=None):
        seen["args"] = [str(a) for a in args]

    monkeypatch.setattr(shorts_mod, "run_ffmpeg", fake_run_ffmpeg)

    shorts_mod._render_segment_dual(
        tmp_path / "camera.mp4",
        tmp_path / "screen.mp4",
        tmp_path / "out.mp4",
        10.0,
        12.5,
        tmp_path / "face-mask.png",
        tmp_path / "screen-mask.png",
        1920,
        1080,
        tmp_path,
    )

    args = seen["args"]
    graph = args[args.index("-filter_complex") + 1]
    assert "-ss" not in args
    assert "trim=start=10.000:end=12.500" in graph
    assert "atrim=start=10.000:end=12.500" in graph


def test_single_source_short_uses_talking_head_916_fill(tmp_path, monkeypatch):
    seen: dict[str, list[str]] = {}

    def fake_run_ffmpeg(args, run_dir=None, receipts=None):
        seen["args"] = [str(a) for a in args]

    monkeypatch.setattr(shorts_mod, "run_ffmpeg", fake_run_ffmpeg)

    shorts_mod._render_segment_talking_head(
        tmp_path / "camera.mp4",
        tmp_path / "out.mp4",
        4.0,
        7.0,
        tmp_path,
    )

    args = seen["args"]
    graph = args[args.index("-filter_complex") + 1]
    assert "-ss" not in args
    assert "trim=start=4.000:end=7.000" in graph
    assert "atrim=start=4.000:end=7.000" in graph
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in graph
    assert "crop=1080:1920" in graph
