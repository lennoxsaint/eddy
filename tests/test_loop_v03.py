"""v0.3 loop: best() ranking on gate-fail, gate-pass maximizes quality, judge no-auto-pass."""

from eddy.config import EddyConfig
from eddy.edit.schema import EditDecisions, Edl, EdlRange
from eddy.loop import _phases
from eddy.loop.state import RunState
from eddy.providers.base import ProviderError
from eddy.qa.judge import run_judge


class _Receipts:
    def log(self, *a, **k):
        pass


def test_gatefail_ranking_prefers_closer_to_feasible(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    # both fail gates: iter1 high quality but far over ceiling; iter2 lower quality but near it
    s.record_attempt(1, False, 9.0, 100, quality=8.0, over_ceiling_s=600)
    s.record_attempt(2, False, 5.0, 50, quality=4.0, over_ceiling_s=60)
    assert s.best()["iteration"] == 2  # closer-to-feasible wins, not the longest/highest-judge


def test_gatepass_ranking_maximizes_quality(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.record_attempt(1, True, 7.0, 10, quality=6.0, over_ceiling_s=0)
    s.record_attempt(2, True, 7.0, 10, quality=8.5, over_ceiling_s=0)
    assert s.best()["iteration"] == 2


def test_gatepass_outranks_higher_quality_gatefail(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.record_attempt(1, False, 9.0, 0, quality=9.5, over_ceiling_s=0)
    s.record_attempt(2, True, 5.0, 0, quality=5.0, over_ceiling_s=0)
    assert s.best()["iteration"] == 2  # a passing edit always beats a failing one


def test_gatepass_over_ceiling_prefers_closer_band(tmp_path):
    # EDD-83: among gate-PASSING but over-ceiling cuts, a materially closer one wins even with
    # slightly lower quality (v0.3 maximized quality here and shipped the LONGEST).
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.record_attempt(1, True, 0, 0, quality=5.556, over_ceiling_s=1694)  # band -14, longer, better q
    s.record_attempt(2, True, 0, 0, quality=5.264, over_ceiling_s=1452)  # band -12, shorter, lower q
    assert s.best()["iteration"] == 2  # closer band wins despite lower quality


def test_gatepass_same_band_defers_to_quality(tmp_path):
    # small length differences (same ~2-min band) still defer to quality — don't sacrifice quality
    # to shave seconds off an already-over-ceiling cut.
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.record_attempt(1, True, 0, 0, quality=5.264, over_ceiling_s=1452)  # band -12
    s.record_attempt(2, True, 0, 0, quality=5.372, over_ceiling_s=1491)  # band -12, higher q
    assert s.best()["iteration"] == 2  # same band -> higher quality wins


def test_under_ceiling_outranks_over_ceiling_gatepass(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.record_attempt(1, True, 0, 0, quality=9.0, over_ceiling_s=600)  # over ceiling, high q
    s.record_attempt(2, True, 0, 0, quality=5.0, over_ceiling_s=0)     # under ceiling (band 0)
    assert s.best()["iteration"] == 2  # under-ceiling (band 0) beats any over-ceiling, regardless of q


def test_compile_failed_stays_worst_feasible(tmp_path):
    # a compile-failed attempt records over_ceiling_s=1e9 -> worst band -> never out-ranks a real cut
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.record_attempt(1, False, 0.0, 0, over_ceiling_s=1e9)                # compile-failed (no edl)
    s.record_attempt(2, False, 5.0, 0, quality=4.0, over_ceiling_s=1500)  # real over-ceiling cut
    assert s.best()["iteration"] == 2


def test_plateau_state_persists(tmp_path):
    (tmp_path / "r").mkdir()
    s = RunState(tmp_path / "r")
    s.set_plateau(2, 7.3)
    assert RunState(tmp_path / "r").data["no_improve"] == 2
    assert RunState(tmp_path / "r").data["prev_best_q"] == 7.3


def test_run_judge_unavailable_does_not_auto_pass(tmp_path):
    class Dead:
        name = "dead"

        def complete(self, *a, **k):
            raise ProviderError("provider down")

    sim = {
        "duration_s": 600, "target_s": 600, "ranges": 1, "removed_total_s": 0,
        "boundary_cards": [],
    }

    class _D:
        class x_eddy:
            beats = []

    res = run_judge(Dead(), _Receipts(), sim, _D(), None, [], None)
    assert res["judge_unstable"] is True
    assert res["weighted"] == 0.0
    assert "advisory_only" not in res  # the auto-pass key is gone


def test_edit_loop_passes_words_to_creator_good_simulation(monkeypatch, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cfg = EddyConfig()
    cfg.loop.max_iterations = 1
    cfg.loop.require_gate_pass = True
    cfg.loop.judge_threshold = 8.0
    cfg.loop.length_ceiling_minutes = 5.0
    words = [
        {"start": 0.0, "end": 0.3, "word": " hello", "probability": 0.99},
        {"start": 0.4, "end": 0.7, "word": " world", "probability": 0.99},
    ]
    phrases = [{"start": 0.0, "end": 0.7, "text": "hello world"}]
    decisions = EditDecisions()
    edl = Edl(sources={"camera": "camera.mp4"}, ranges=[EdlRange(start=0.0, end=1.0)], total_duration_s=1.0)
    captured = {}

    monkeypatch.setattr(_phases, "load_config", lambda: cfg)
    monkeypatch.setattr(_phases, "get_editorial_provider", lambda cfg, receipts: object())
    monkeypatch.setattr(_phases, "_record_model_pin", lambda *args, **kwargs: None)
    monkeypatch.setattr(_phases, "manifest", lambda rd: {"run_settings": {}})
    monkeypatch.setattr(_phases, "words_flat", lambda rd: words)
    monkeypatch.setattr(_phases, "load_phrases", lambda rd: phrases)
    monkeypatch.setattr(_phases, "beat_map", lambda *args, **kwargs: [])
    monkeypatch.setattr(_phases, "initial_decisions", lambda *args, **kwargs: decisions)
    monkeypatch.setattr(_phases, "compile_with_repair", lambda *args, **kwargs: (decisions, edl))

    def fake_simulate(_edl, _decisions, _phrases, _cfg, _target_s, words=None):
        captured["words"] = words
        return {
            "duration_s": 1.0,
            "target_s": 60.0,
            "ranges": 1,
            "removed_total_s": 0.0,
            "boundary_cards": [],
            "verdicts": {
                "no_dead_air": True,
                "handles_safe": True,
                "retake_clean": True,
                "gap_pacing": True,
                "has_content": True,
            },
            "pass": True,
        }

    monkeypatch.setattr(_phases, "simulate", fake_simulate)
    monkeypatch.setattr(_phases, "render_edl", lambda edl, out, *args, **kwargs: out.write_text("proxy") or out)
    monkeypatch.setattr(_phases, "boundary_contact_sheet", lambda *args, **kwargs: run_dir / "contact.jpg")
    monkeypatch.setattr(_phases, "run_deterministic", lambda *args, **kwargs: {"pass": True})
    monkeypatch.setattr(_phases, "save_qa", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        _phases,
        "run_judge",
        lambda *args, **kwargs: {
            "weighted": 10.0,
            "judge_unstable": False,
            "defects": [],
            "scores": {},
        },
    )
    monkeypatch.setattr(_phases, "quality_score", lambda *args, **kwargs: {"quality": 10.0, "components": {}})

    chosen = _phases.edit_loop(run_dir)

    assert captured["words"] is words
    assert chosen == run_dir / "iterations" / "01"


def test_edit_loop_forwards_resolved_ceiling_to_ensemble(monkeypatch, tmp_path):
    # v1.7.3 follow-up: when the ensemble path is taken (ensemble_n>1 + focus_mode="extract"), the
    # loop's own resolved per-run ceiling (brief-parsed / format, not the static config default)
    # must reach best_of_n_decisions, so its selector agrees with the loop's under_ceiling gate.
    import eddy.edit.ensemble as ensemble_mod

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cfg = EddyConfig()
    cfg.loop.max_iterations = 1
    cfg.loop.require_gate_pass = True
    cfg.loop.judge_threshold = 8.0
    cfg.loop.length_ceiling_minutes = 14.0  # static default; the per-run ceiling below must win
    cfg.loop.ensemble_n = 2
    decisions = EditDecisions()
    edl = Edl(sources={"camera": "camera.mp4"}, ranges=[EdlRange(start=0.0, end=1.0)], total_duration_s=1.0)
    captured = {}

    monkeypatch.setattr(_phases, "load_config", lambda: cfg)
    monkeypatch.setattr(_phases, "get_editorial_provider", lambda cfg, receipts: object())
    monkeypatch.setattr(_phases, "_record_model_pin", lambda *args, **kwargs: None)
    monkeypatch.setattr(_phases, "manifest", lambda rd: {"run_settings": {}})
    monkeypatch.setattr(_phases, "words_flat", lambda rd: [])
    monkeypatch.setattr(_phases, "load_phrases", lambda rd: [])
    monkeypatch.setattr(_phases, "beat_map", lambda *args, **kwargs: [])
    monkeypatch.setattr(_phases, "compile_with_repair", lambda *args, **kwargs: (decisions, edl))

    def fake_best_of_n(*args, **kwargs):
        captured["ceiling_minutes"] = kwargs.get("ceiling_minutes")
        return decisions

    monkeypatch.setattr(ensemble_mod, "best_of_n_decisions", fake_best_of_n)
    monkeypatch.setattr(_phases, "simulate", lambda *a, **k: {
        "duration_s": 1.0, "target_s": 60.0, "ranges": 1, "removed_total_s": 0.0, "boundary_cards": [],
        "verdicts": {}, "pass": True,
    })
    monkeypatch.setattr(_phases, "render_edl", lambda edl, out, *a, **k: out.write_text("proxy") or out)
    monkeypatch.setattr(_phases, "boundary_contact_sheet", lambda *a, **k: run_dir / "contact.jpg")
    monkeypatch.setattr(_phases, "run_deterministic", lambda *a, **k: {"pass": True})
    monkeypatch.setattr(_phases, "save_qa", lambda *a, **k: None)
    monkeypatch.setattr(
        _phases, "run_judge",
        lambda *a, **k: {"weighted": 10.0, "judge_unstable": False, "defects": [], "scores": {}},
    )
    monkeypatch.setattr(_phases, "quality_score", lambda *a, **k: {"quality": 10.0, "components": {}})

    _phases.edit_loop(run_dir, ceiling_minutes=6.0, focus="explain X", focus_mode="extract")

    assert captured["ceiling_minutes"] == 6.0
