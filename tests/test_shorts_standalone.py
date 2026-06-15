"""v0.8: standalone `eddy shorts <source>` — transcribe -> one decision pass -> render shorts only,
skipping the iterative edit loop and the long-form render. Orchestration is mocked at the stage
boundaries; this asserts the sequence and that the long edit_loop is NOT invoked."""

import eddy.edit.cutplan as cutplan_mod
import eddy.loop.controller as ctrl
import eddy.render.shorts as shorts_mod


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
