"""v0.4: crash-safe run state. Atomic writes + tolerant loaders so a torn state.json /
receipts.jsonl from a SIGKILL/OOM/power-loss mid-write can't make --resume crash and lose work.
"""

from eddy.atomicio import atomic_write_text
from eddy.loop.receipts import Receipts
from eddy.loop.state import RunState


def test_atomic_write_replaces_and_leaves_no_tmp(tmp_path):
    p = tmp_path / "state.json"
    atomic_write_text(p, '{"a": 1}')
    assert p.read_text() == '{"a": 1}'
    atomic_write_text(p, '{"a": 2}')
    assert p.read_text() == '{"a": 2}'
    assert not (tmp_path / "state.json.tmp").exists()


def test_runstate_save_is_atomic_roundtrip(tmp_path):
    s = RunState(tmp_path)
    s.data["phase"] = "loop_done"
    s.data["iteration"] = 4
    s.save()
    assert not (tmp_path / "state.json.tmp").exists()
    reloaded = RunState(tmp_path)
    assert reloaded.data["phase"] == "loop_done"
    assert reloaded.data["iteration"] == 4
    assert reloaded.recovered is False


def test_runstate_tolerates_truncated_state(tmp_path):
    (tmp_path / "state.json").write_text('{"iteration": 7, "attempts": [')  # torn mid-write
    s = RunState(tmp_path)
    assert s.recovered is True
    assert s.data == {"iteration": 0, "attempts": [], "best_iter": None, "phase": "created"}


def test_runstate_tolerates_non_object_json(tmp_path):
    (tmp_path / "state.json").write_text("[]")
    s = RunState(tmp_path)
    assert s.recovered is True
    assert s.data["phase"] == "created"


def test_runstate_clean_load_not_flagged_recovered(tmp_path):
    (tmp_path / "state.json").write_text('{"iteration": 3, "attempts": [], "best_iter": 2, "phase": "x"}')
    s = RunState(tmp_path)
    assert s.recovered is False
    assert s.data["best_iter"] == 2


def test_receipts_read_skips_torn_line(tmp_path):
    r = Receipts(tmp_path)
    r.log("a", x=1)
    r.log("b", y=2)
    with r.path.open("a") as f:
        f.write('{"event": "c", "z":')  # interrupted append, no newline-terminated object
    out = r.read()
    assert [e["event"] for e in out] == ["a", "b"]
