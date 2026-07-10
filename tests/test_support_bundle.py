import tarfile
from pathlib import Path

from eddy.support import create_support_bundle


def test_support_bundle_contains_receipts_but_never_media_or_secrets(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "state.json").write_text('{"state":"blocked"}\n')
    (run / "receipts.jsonl").write_text('{"event":"failed","token":"sk-secret-value"}\n')
    (run / "proxy.mp4").write_bytes(b"media")
    output = tmp_path / "support.tar.gz"

    create_support_bundle(run, output)

    with tarfile.open(output, "r:gz") as archive:
        names = archive.getnames()
        assert "state.json" in names
        assert "receipts.jsonl" in names
        assert "proxy.mp4" not in names
        receipts = archive.extractfile("receipts.jsonl")
        assert receipts is not None
        assert b"sk-secret-value" not in receipts.read()
