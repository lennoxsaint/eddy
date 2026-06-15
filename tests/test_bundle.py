"""v0.7: eddy bundle — redacted diagnostic archive. PII (transcript text + home paths) is stripped;
the audit trail (hashes, gates, scores) is kept; no footage/transcript/faces are included."""

import json
import zipfile

from eddy.bundle import _redact, _scrub, build_bundle


def test_scrub_home_paths():
    assert _scrub("/Users/lennox/footage/secret.mp4") == "[home]"  # whole path incl. filename
    assert _scrub("/home/bob/x.mp4") == "[home]"
    assert _scrub("relative/ok.mp4") == "relative/ok.mp4"  # no home root -> untouched


def test_redact_strips_text_keeps_structure():
    obj = {"quote": "my secret line", "start_s": 1.2, "tier": "MANDATORY",
           "defects": [{"reason": "orphaned payoff", "severity": "major"}]}
    r = _redact(obj)
    assert r["quote"] == "[redacted]" and r["start_s"] == 1.2 and r["tier"] == "MANDATORY"
    assert r["defects"][0]["reason"] == "[redacted]" and r["defects"][0]["severity"] == "major"


def _seed(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "sources": {"camera": "/Users/lennox/footage/secret-project.mp4"},
        "source_sha256": {"camera": "abc123"},
    }))
    (run_dir / "state.json").write_text(json.dumps({"phase": "done", "iteration": 3}))
    (run_dir / "receipts.jsonl").write_text(
        json.dumps({"event": "model_call", "label": "cutplan", "ok": True}) + "\n"
        + json.dumps({"event": "gate", "quality": 7.2, "judge_score": 8.1}) + "\n"
    )
    it = run_dir / "iterations" / "01"
    it.mkdir(parents=True)
    (it / "judge.json").write_text(json.dumps({"weighted": 8.0, "defects": [{"quote": "secret quote", "severity": "minor"}]}))


def test_build_bundle_redacts_and_keeps_audit(tmp_path):
    run = tmp_path / "run"
    _seed(run)
    out = build_bundle(run)
    assert out.exists() and out.suffix == ".zip"

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "environment.json" in names and "manifest.json" in names and "receipts.jsonl" in names
        manifest = z.read("manifest.json").decode()
        assert "abc123" in manifest                 # hash kept (useful for triage)
        assert "secret-project.mp4" not in manifest # but the home path is scrubbed
        assert "[home]" in manifest
        judge = z.read("iterations/01/judge.json").decode()
        assert "secret quote" not in judge and "[redacted]" in judge and "8.0" in judge
        env = json.loads(z.read("environment.json"))
        assert "eddy_version" in env and "platform" in env
        # no raw footage / transcript / words anywhere in the bundle
        assert not any(n.endswith((".mp4", ".wav", ".png", "words.json", "transcript.md")) for n in names)
