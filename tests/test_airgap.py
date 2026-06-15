"""v1.0 GA: guard the offline/air-gap install path — a fully-pinned lockfile + the wheelhouse
builder + the airgap doc must stay present and consistent, since offline install depends on them."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_requirements_lock_is_fully_pinned():
    lock = (ROOT / "requirements.lock").read_text().strip().splitlines()
    assert lock, "requirements.lock must not be empty (offline install needs the dep closure)"
    pin = re.compile(r"^[A-Za-z0-9._-]+==[0-9][^\s]*$")
    for line in lock:
        assert pin.match(line), f"unpinned/loose lock line: {line!r}"


def test_runtime_deps_are_in_the_lock():
    lock = (ROOT / "requirements.lock").read_text().lower()
    for pkg in ("typer", "pydantic", "pillow", "openai", "anthropic", "faster-whisper", "httpx"):
        assert pkg in lock, f"runtime dep {pkg} missing from requirements.lock"


def test_wheelhouse_builder_present_and_executable():
    s = ROOT / "scripts" / "build_wheelhouse.sh"
    assert s.exists()
    assert s.stat().st_mode & 0o111, "build_wheelhouse.sh must be executable"
    body = s.read_text()
    assert "--no-index" in body and "requirements.lock" in body


def test_airgap_doc_covers_the_four_stages():
    doc = (ROOT / "docs" / "AIRGAP.md").read_text().lower()
    for needle in ("wheelhouse", "--no-index", "ffmpeg", "ollama", "local_files_only", "--local-only"):
        assert needle in doc, f"AIRGAP.md should mention {needle}"
