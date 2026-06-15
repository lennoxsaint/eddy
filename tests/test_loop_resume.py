"""Resume integrity: plateau/attempt state survives a save/reload round-trip, torn state.json
recovers, and a changed editorial brain on reopen logs model_drift. No real loop runs here —
transcribe/render are never invoked; RunState lives in tmp_path and we exercise the pure
persistence + pin logic directly."""

import json

from eddy.config import load_config
from eddy.loop.controller import _record_model_pin
from eddy.loop.state import RunState


class _Receipts:
    """Captures (event, fields) so a test can assert the exact drift payload, not just that
    a log happened."""

    def __init__(self):
        self.events = []

    def log(self, event, **f):
        self.events.append((event, f))


def test_set_plateau_persists_full_triple_and_best_over(tmp_path):
    # set_plateau persists no_improve / prev_best_q / best_over; a FRESH RunState reads them back.
    # (existing test_loop_v03 only checks no_improve+prev_best_q — this pins best_over too, the
    # length-convergence axis the feasibility-gated plateau resumes from.)
    s = RunState(tmp_path)
    s.set_plateau(3, 7.42, best_over=915.0)

    reloaded = RunState(tmp_path)
    assert reloaded.data["no_improve"] == 3
    assert reloaded.data["prev_best_q"] == 7.42
    assert reloaded.data["best_over"] == 915.0


def test_set_plateau_without_best_over_leaves_it_unset(tmp_path):
    # best_over is only written when explicitly passed — a None call must not stamp a key the
    # resume path would then read as a real (and wrong) convergence floor.
    s = RunState(tmp_path)
    s.set_plateau(1, 4.0)
    assert "best_over" not in RunState(tmp_path).data


def test_record_attempt_and_best_survive_reload(tmp_path):
    # record_attempt + best() ranking survive a save/reload round-trip: a fresh RunState reading
    # the persisted attempts must pick the SAME best() the writer would have.
    s = RunState(tmp_path)
    s.record_attempt(1, True, 7.0, 10, quality=6.0, over_ceiling_s=0)
    s.record_attempt(2, True, 7.0, 10, quality=8.5, over_ceiling_s=0)

    reloaded = RunState(tmp_path)
    assert len(reloaded.data["attempts"]) == 2
    assert reloaded.data["best_iter"] == 2
    assert reloaded.best()["iteration"] == 2
    assert reloaded.best()["quality"] == 8.5


def test_record_attempt_reload_preserves_over_ceiling_ranking(tmp_path):
    # the feasibility band that drives best() must survive the round-trip: a closer-to-ceiling cut
    # recorded earlier still out-ranks a longer, higher-quality one after reload (regression guard
    # against over_ceiling_s being dropped on persist).
    s = RunState(tmp_path)
    s.record_attempt(1, False, 9.0, 100, quality=8.0, over_ceiling_s=600)
    s.record_attempt(2, False, 5.0, 50, quality=4.0, over_ceiling_s=60)

    reloaded = RunState(tmp_path)
    assert reloaded.best()["iteration"] == 2
    assert reloaded.best()["over_ceiling_s"] == 60


def test_torn_state_json_sets_recovered_and_preserves_a_clean_resave(tmp_path):
    # a state.json torn mid-write must not crash --resume: RunState flags recovered, falls back to
    # a fresh default, and a subsequent record+save writes valid JSON the next open reads cleanly.
    (tmp_path / "state.json").write_text('{"iteration": 9, "attempts": [{"iter')  # torn append
    s = RunState(tmp_path)
    assert s.recovered is True
    assert s.data["iteration"] == 0
    assert s.data["attempts"] == []

    s.record_attempt(1, True, 8.0, 5, quality=7.0, over_ceiling_s=0)
    recovered_clean = RunState(tmp_path)
    assert recovered_clean.recovered is False  # the resaved file is valid JSON again
    assert recovered_clean.best()["iteration"] == 1


def test_record_model_pin_logs_drift_on_changed_brain_with_payload(tmp_path):
    # reopening a run whose model-pin.json was written by a DIFFERENT editorial brain logs
    # model_drift carrying both prior and current identities — the honest "it got worse on re-run
    # is a silent model change" signal. editorial set explicitly so no PATH/provider auto-resolve.
    (tmp_path / "model-pin.json").write_text(
        json.dumps({"provider": "ollama", "model": "qwen36-27b-codex:q4"})
    )
    cfg = load_config()
    cfg.provider.editorial = "anthropic"
    cfg.provider.anthropic.model = "claude-haiku-changed"

    receipts = _Receipts()
    _record_model_pin(tmp_path, cfg, receipts)

    drift = [f for e, f in receipts.events if e == "model_drift"]
    assert len(drift) == 1
    assert drift[0]["prior"] == {"provider": "ollama", "model": "qwen36-27b-codex:q4"}
    assert drift[0]["current"] == {"provider": "anthropic", "model": "claude-haiku-changed"}
    # an existing pin file is never overwritten on reopen, and no fresh model_pin is logged
    assert json.loads((tmp_path / "model-pin.json").read_text())["model"] == "qwen36-27b-codex:q4"
    assert not any(e == "model_pin" for e, _ in receipts.events)


def test_record_model_pin_same_brain_on_reopen_is_silent(tmp_path):
    # reopening with the SAME editorial brain must NOT log drift — only a genuine change is a signal.
    cfg = load_config()
    cfg.provider.editorial = "anthropic"
    cfg.provider.anthropic.model = "claude-haiku-stable"
    _record_model_pin(tmp_path, cfg, _Receipts())  # first write

    reopen = _Receipts()
    _record_model_pin(tmp_path, cfg, reopen)  # same brain
    assert not any(e == "model_drift" for e, _ in reopen.events)
    assert not any(e == "model_pin" for e, _ in reopen.events)  # not re-pinned on reopen
