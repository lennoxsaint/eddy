"""v0.8: batch/queue runner — many sources, per-item failure recovery, structured summary; fleet list."""

import json

from eddy.batch import discover_batch_sources, list_runs, run_batch


def test_discover_batch_sources_subdirs_and_videos(tmp_path):
    (tmp_path / "shootA").mkdir()
    (tmp_path / "shootB").mkdir()
    (tmp_path / "standalone.mp4").write_bytes(b"x")
    found = discover_batch_sources(tmp_path)
    names = {p.name for p in found}
    assert names == {"shootA", "shootB", "standalone.mp4"}


def test_discover_single_dir_of_videos_is_one_source(tmp_path):
    (tmp_path / "camera.mp4").write_bytes(b"x")
    (tmp_path / "screen.mp4").write_bytes(b"x")  # a footage dir, no subdirs -> one source
    assert discover_batch_sources(tmp_path) == [tmp_path]


def test_run_batch_continues_past_failures():
    processed = []

    def runner(source, **opts):
        processed.append(source)
        if "bad" in str(source):
            raise RuntimeError("boom")

    summary = run_batch(["a", "bad-b", "c"], runner=runner)
    assert processed == ["a", "bad-b", "c"]  # did not stop at the failure
    assert summary["total"] == 3 and summary["succeeded"] == 2 and summary["failed"] == 1
    failed = [i for i in summary["items"] if i["status"] == "failed"]
    assert failed[0]["source"] == "bad-b" and "error" in failed[0]


def test_list_runs(tmp_path):
    r1 = tmp_path / "2026-06-16-a"
    r1.mkdir()
    (r1 / "manifest.json").write_text("{}")
    (r1 / "state.json").write_text(json.dumps({"phase": "done", "best_iter": 3}))
    (tmp_path / "not-a-run").mkdir()  # no manifest -> excluded
    rows = list_runs(tmp_path)
    assert len(rows) == 1
    assert rows[0]["slug"] == "2026-06-16-a" and rows[0]["phase"] == "done" and rows[0]["best_iter"] == 3
