"""v1.0 GA: the release/support/known-limits docs must exist and cover the load-bearing topics, so
a release isn't cut with a missing or hollow runbook."""

from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_release_doc_covers_gate_and_human_gate():
    t = (DOCS / "RELEASE.md").read_text().lower()
    for needle in ("required-green", "coverage", "golden", "notariz", "authenticode", "pipx", "rollback"):
        assert needle in t, f"RELEASE.md should mention {needle}"


def test_support_runbook_covers_triage_flow():
    t = (DOCS / "SUPPORT.md").read_text().lower()
    for needle in ("eddy doctor", "--dry-run", "eddy bundle", "egressblocked", "--resume"):
        assert needle in t, f"SUPPORT.md should mention {needle}"


def test_known_limits_covers_documented_gaps():
    t = (DOCS / "KNOWN-LIMITS.md").read_text().lower()
    for needle in ("single-speaker", "rtl", "audio-first", "reproducib", "edd-84"):
        assert needle in t, f"KNOWN-LIMITS.md should mention {needle}"


def test_edd84_documented_in_decision_log():
    t = (DOCS / "decision-log.md").read_text().lower()
    assert "edd-84" in t  # disposition recorded, not silently dropped
