import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_scrub_module():
    path = ROOT / "scripts" / "public_scrub_check.py"
    spec = importlib.util.spec_from_file_location("public_scrub_check", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_scrub_passes_current_tracked_files():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "public_scrub_check.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_public_scrub_scans_vendor_paths(tmp_path, monkeypatch):
    scrub = _load_scrub_module()
    monkeypatch.setattr(scrub, "ROOT", tmp_path)
    leaked = tmp_path / "vendor" / "yt_tools" / "example.py"
    leaked.parent.mkdir(parents=True)
    leaked.write_text('ROOT = Path("' + "/Users/" + 'yassybabes/YouTube")\n', encoding="utf-8")

    findings = scrub.scan_file(leaked)

    assert {finding["type"] for finding in findings} == {"absolute_yassy_path"}


def test_public_scrub_flags_realistic_private_tokens(tmp_path, monkeypatch):
    scrub = _load_scrub_module()
    monkeypatch.setattr(scrub, "ROOT", tmp_path)
    leaked = tmp_path / "notes.md"
    leaked.write_text(
        "\n".join(
            [
                "tf_" + "mcp_a0a400eb02d0",
                "dx_" + "bearer_7afa4666-5ed3-481f-8974-a6f77c32da50",
                "sk-" + "ant-api03-this-is-a-long-fake-test-token",
            ]
        ),
        encoding="utf-8",
    )

    findings = scrub.scan_file(leaked)

    assert {finding["type"] for finding in findings} == {
        "threadify_mcp_token",
        "descript_token",
        "openai_key",
        "anthropic_key",
    }
