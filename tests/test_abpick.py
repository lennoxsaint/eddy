"""v0.8: deterministic A/B title pick (reusable rubric) + honest thumbnail pairing."""

import json

from eddy.package.abpick import build_ab_pick, pick_ab, pick_thumbnail_ab, score_title


def test_score_rewards_length_number_curiosity():
    strong = score_title("Why 3 Simple Habits Beat Every Productivity App")  # number + curiosity + fit
    weak = score_title("Thoughts")
    assert strong["score"] > weak["score"]
    assert strong["signals"].get("has_number") and strong["signals"].get("curiosity")


def test_score_penalizes_shouty_titles():
    shouty = score_title("BUY THIS NOW!!! YOU WONT BELIEVE WHAT HAPPENED NEXT!!!")
    assert "clean" not in shouty["signals"]


def test_pick_ab_picks_divergent_b():
    titles = [
        {"title": "Why 3 Simple Habits Beat Every Productivity App"},
        {"title": "Why 3 Simple Habits Beat Every Productivity Tool"},  # near-duplicate of A
        {"title": "The Hidden Cost of Saying Yes to Everything"},       # divergent
    ]
    res = pick_ab(titles)
    assert res["a"]["title"] == "Why 3 Simple Habits Beat Every Productivity App"
    # B must diverge from A, so the near-duplicate is skipped for the divergent option
    assert res["b"]["title"] == "The Hidden Cost of Saying Yes to Everything"
    assert res["divergence"] >= 0.5


def test_pick_ab_flags_weak_test_when_all_overlap():
    titles = [
        {"title": "How To Edit Video Faster With AI Tools Today"},
        {"title": "How To Edit Video Faster With AI Tools Now"},
    ]
    res = pick_ab(titles)
    assert res["a"] and res["b"]
    assert "weak" in res["note"]  # both overlap -> honest weak-test flag


def test_pick_ab_empty():
    res = pick_ab([])
    assert res["a"] is None and res["b"] is None


def test_pick_thumbnail_ab(tmp_path):
    assert pick_thumbnail_ab(tmp_path)["a"] is None  # none generated
    (tmp_path / "gemini-1.png").write_bytes(b"x")
    (tmp_path / "openai-1.png").write_bytes(b"x")
    res = pick_thumbnail_ab(tmp_path)
    assert {res["a"], res["b"]} == {"gemini-1.png", "openai-1.png"}


def test_build_ab_pick_standalone_from_titles_json(tmp_path):
    final = tmp_path / "final"
    final.mkdir()
    (final / "titles.json").write_text(json.dumps([
        {"title": "Why 3 Simple Habits Beat Every Productivity App"},
        {"title": "The Hidden Cost of Saying Yes to Everything"},
    ]))
    out = build_ab_pick(tmp_path)  # no titles arg -> reads titles.json
    res = json.loads(out.read_text())
    assert res["title"]["a"]["title"] and res["title"]["b"]["title"]
    assert (final / "AB-TEST.md").exists()
