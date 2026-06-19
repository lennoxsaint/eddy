"""v1.7 best-of-N self-consistency selection logic (eddy.edit.ensemble).

These tests pin the DETERMINISTIC selection behavior with fakes — no model calls, no render — so the
variance-reduction mechanism (max-of-N under a fixed key) is verified independent of the slow brain.
"""

from types import SimpleNamespace

from eddy.edit.compiler import CompileError
import eddy.edit.ensemble as ens


class FakeReceipts:
    def __init__(self):
        self.events = []

    def log(self, event, **kw):
        self.events.append((event, kw))


def test_ensemble_is_off_by_default():
    # default ensemble_n==1 -> the loop takes the single-draft path -> normal/extract edits are
    # byte-identical to pre-v1.7. The lever is strictly opt-in via config.
    from eddy.config import LoopConfig
    assert LoopConfig().ensemble_n == 1


def _edl(n_ranges=1, dur=120.0):
    return SimpleNamespace(ranges=[object()] * n_ranges, total_duration_s=dur)


def _patch_phrases(monkeypatch):
    monkeypatch.setattr(ens, "load_phrases", lambda rd: [])


# --- selector key ordering ---------------------------------------------------------------------

def test_selector_key_band_beats_all():
    # an under-ceiling draft (band 0) outranks an over-ceiling one even with a higher objective + fewer blocks
    assert ens._selector_key(5.0, 0.0, 12) > ens._selector_key(9.9, 300.0, 2)


def test_selector_key_same_band_prefers_fewer_blocks_over_objective():
    # v1.7.1: among feasible drafts the more contiguous (fewer-block) extract wins even when the bloated
    # draft scores a higher objective — the confirm-d4 fix (77-block obj 9.1 lost to 18-block obj 8.1).
    assert ens._selector_key(8.1, 0.0, 18) > ens._selector_key(9.1, 0.0, 77)


def test_selector_key_objective_breaks_block_ties():
    # same band + same block count -> higher objective wins (objective is only the final tiebreak now)
    assert ens._selector_key(8.0, 0.0, 5) > ens._selector_key(6.0, 0.0, 5)


# --- best_of_n selection ------------------------------------------------------------------------

def test_best_of_n_picks_highest_key(monkeypatch):
    _patch_phrases(monkeypatch)
    drafts = [SimpleNamespace(idx=i) for i in range(3)]
    seq = iter(drafts)
    monkeypatch.setattr(ens, "initial_decisions", lambda *a, **k: next(seq))
    keymap = {0: (0, 6.0, -10), 1: (0, 8.5, -4), 2: (0, 7.0, -6)}  # draft 1 is best

    def fake_score(run_dir, d, *a, **k):
        return d, _edl(1), {}, {"objective": 0.0, "over_ceiling_s": 0.0}, keymap[d.idx]

    monkeypatch.setattr(ens, "score_draft", fake_score)
    r = FakeReceipts()
    out = ens.best_of_n_decisions("rd", object(), r, 120.0, [], [], [], object(), n=3)
    assert out.idx == 1
    assert sum(1 for e in r.events if e[0] == "ensemble_draft") == 3
    assert any(e[0] == "ensemble_pick" and e[1]["draft"] == 1 for e in r.events)


def test_best_of_n_skips_failed_drafts(monkeypatch):
    _patch_phrases(monkeypatch)
    drafts = [SimpleNamespace(idx=i) for i in range(3)]
    seq = iter(drafts)
    monkeypatch.setattr(ens, "initial_decisions", lambda *a, **k: next(seq))

    def fake_score(run_dir, d, *a, **k):
        if d.idx in (0, 2):
            raise CompileError([{"why": "bad"}])
        return d, _edl(1), {}, {"objective": 5.0, "over_ceiling_s": 0.0}, (0, 5.0, -3)

    monkeypatch.setattr(ens, "score_draft", fake_score)
    r = FakeReceipts()
    out = ens.best_of_n_decisions("rd", object(), r, 120.0, [], [], [], object(), n=3)
    assert out.idx == 1  # only the one that compiled
    assert sum(1 for e in r.events if e[0] == "ensemble_draft_failed") == 2


def test_best_of_n_all_fail_falls_back_to_single_draft(monkeypatch):
    _patch_phrases(monkeypatch)
    drafts = [SimpleNamespace(idx=i) for i in range(4)]  # 3 ensemble + 1 fallback
    seq = iter(drafts)
    monkeypatch.setattr(ens, "initial_decisions", lambda *a, **k: next(seq))

    def always_fail(*a, **k):
        raise CompileError([{"why": "x"}])

    monkeypatch.setattr(ens, "score_draft", always_fail)
    r = FakeReceipts()
    out = ens.best_of_n_decisions("rd", object(), r, 120.0, [], [], [], object(), n=3)
    assert out.idx == 3  # the fallback draft (sampled after the 3 failed ensemble drafts)
    assert any(e[0] == "ensemble_all_failed" for e in r.events)


def test_n_le_1_samples_exactly_one_draft(monkeypatch):
    _patch_phrases(monkeypatch)
    calls = {"n": 0}

    def fake_init(*a, **k):
        calls["n"] += 1
        return SimpleNamespace(idx=0)

    monkeypatch.setattr(ens, "initial_decisions", fake_init)
    monkeypatch.setattr(
        ens, "score_draft",
        lambda run_dir, d, *a, **k: (d, _edl(1), {}, {"objective": 5.0, "over_ceiling_s": 0.0}, (0, 5.0, -1)),
    )
    ens.best_of_n_decisions("rd", object(), FakeReceipts(), 1.0, [], [], [], object(), n=1)
    assert calls["n"] == 1  # no extra drafts when n<=1
