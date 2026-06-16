"""v1.4: fixture-backed e2e for package_run() — the launch-kit assembler.

Builds a minimal but VALID run (compiled edl + decisions + phrases), stubs the editorial brain, and
asserts the whole kit is assembled (copy, A/B, transcript, subtitles, benchmark, NLE timeline,
disclosure, index) and that a brain failure can't lose the kit. Protects the v1.4 copy fallbacks
(#4) and any future change to the assembler ordering."""

from __future__ import annotations

import json

from eddy.config import GatesConfig, RenderConfig, load_config
from eddy.edit.compiler import compile_edl
from eddy.edit.schema import Cut, EditDecisions
from eddy.package.launch_kit import package_run


class _FakeProvider:
    """Canned editorial copy, routed by the response schema so it never mis-answers a stage."""

    def complete(self, messages, schema=None, max_tokens=None):
        props = (schema or {}).get("properties", {})
        if "labels" in props:
            return {"labels": ["Intro", "The Idea", "Wrap"]}
        if "titles" in props:
            return {"titles": [{
                "title": "The One Habit That Changed Everything",
                "grounding_quote": "this is phrase 0 about the main idea",
                "mechanism": "specificity", "rationale": "curiosity gap",
            }]}
        if "description" in props:
            return {"description": "A short description of the video."}
        return {}


class _DeadProvider:
    def complete(self, *a, **k):
        raise RuntimeError("brain down")


def _words(n: int = 100, word_s: float = 0.3, gap_s: float = 0.1) -> list[dict]:
    words, t = [], 0.0
    for i in range(n):
        words.append({"start": round(t, 3), "end": round(t + word_s, 3), "word": f" w{i}", "probability": 0.9})
        t += word_s + gap_s
    return words


def _build_run(tmp_path):
    run_dir = tmp_path / "2026-demo"
    (run_dir / "iterations" / "01").mkdir(parents=True)
    (run_dir / "transcript").mkdir(parents=True)
    (run_dir / "final").mkdir(parents=True)

    words = _words()
    total = words[-1]["end"] + 1.0
    decisions = EditDecisions(cuts=[Cut(start_s=words[30]["start"], end_s=words[49]["end"], tier="MANDATORY")])
    edl = compile_edl(decisions, words, "cam.mp4", total, RenderConfig(), GatesConfig(), tighten_gaps=False)

    (run_dir / "iterations" / "01" / "edit-decisions.json").write_text(decisions.model_dump_json())
    (run_dir / "iterations" / "01" / "edl.json").write_text(edl.model_dump_json())
    phrases = [
        {"start": words[i]["start"], "end": words[min(i + 9, len(words) - 1)]["end"],
         "text": f"this is phrase {i} talking about the main idea here"}
        for i in range(0, 100, 10)
    ]
    (run_dir / "transcript" / "phrases.json").write_text(json.dumps(phrases))
    return run_dir


def _patch_env(monkeypatch, tmp_path, provider):
    cfg = load_config()
    cfg.paths.runs_dir = str(tmp_path)
    monkeypatch.setattr("eddy.package.launch_kit.load_config", lambda: cfg)
    monkeypatch.setattr("eddy.package.launch_kit.get_provider", lambda c: provider)


def test_package_run_assembles_the_full_kit(tmp_path, monkeypatch):
    run_dir = _build_run(tmp_path)
    _patch_env(monkeypatch, tmp_path, _FakeProvider())

    out = package_run(run_dir)
    final = run_dir / "final"
    for name in (
        "titles.md", "titles.json", "description.md", "chapters.txt", "transcript.md",
        "subtitles.srt", "subtitles.vtt", "AI-DISCLOSURE.md", "REVIEW.md",
        "edit-decisions.benchmark.json", "timeline.edl", "ab-pick.json",
    ):
        assert (final / name).exists(), f"missing kit artifact: {name}"
    assert out.name == "launch-kit" and (out / "LAUNCH-KIT.md").exists()
    # receipts captured the assembly, and the index carries the model-written title
    assert "launch_kit" in (run_dir / "receipts.jsonl").read_text()
    assert "The One Habit" in (out / "LAUNCH-KIT.md").read_text()


def test_package_run_survives_a_brain_failure(tmp_path, monkeypatch):
    # a dead brain must NOT lose the kit after a good edit — titles/description fall back (v1.4 #4)
    run_dir = _build_run(tmp_path)
    _patch_env(monkeypatch, tmp_path, _DeadProvider())

    out = package_run(run_dir)
    assert (out / "LAUNCH-KIT.md").exists()
    assert (run_dir / "final" / "titles.md").exists()
    assert (run_dir / "final" / "description.md").read_text().strip()
