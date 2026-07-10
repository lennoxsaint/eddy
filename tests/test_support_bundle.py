import tarfile
from pathlib import Path

from eddy.support import create_support_bundle


def test_support_bundle_contains_receipts_but_never_media_or_secrets(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "state.json").write_text('{"state":"blocked"}\n')
    (run / "receipts.jsonl").write_text(
        '{"event":"failed","token":"sk-secret-value","detail":"private speech"}\n'
    )
    provider_dir = run / "quarantine" / "attempt-1"
    provider_dir.mkdir(parents=True)
    (provider_dir / "provider-receipts.jsonl").write_text(
        '{"event":"descript_provider","provider":"descript_api",'
        '"project_id":"private-project","composition_id":"private-composition"}\n'
        '{"event":"descript_effect_survival","status":"failed",'
        '"blockers":["descript_quality_not_studio_sound"],'
        '"metrics":{"echo_score":0.6483,"normalized_correlation":0.8404}}\n'
    )
    (run / "repair-packet.json").write_text(
        '{"attempt":1,"remaining_attempts":2,"gates":{"motion":false},'
        '"blockers":["motion_failed"],"quarantine":"/Users/private/run"}\n'
    )
    (run / "transcript.json").write_text('{"words":["private speech"]}\n')
    (run / "worker.log").write_text("Bearer private-token-value user@example.com /Users/me/file\n")
    (run / "proxy.mp4").write_bytes(b"media")
    output = tmp_path / "support.tar.gz"

    create_support_bundle(run, output)

    with tarfile.open(output, "r:gz") as archive:
        names = archive.getnames()
        assert "state.json" in names
        assert "receipts.jsonl" in names
        assert "repair-packet.json" in names
        assert "quarantine/attempt-1/provider-receipts.jsonl" in names
        assert "proxy.mp4" not in names
        assert "transcript.json" not in names
        assert "worker.log" not in names
        receipts = archive.extractfile("receipts.jsonl")
        assert receipts is not None
        receipt_bytes = receipts.read()
        assert b"sk-secret-value" not in receipt_bytes
        assert b"private speech" not in receipt_bytes
        repair = archive.extractfile("repair-packet.json")
        assert repair is not None
        repair_bytes = repair.read()
        assert b"motion_failed" in repair_bytes
        assert b"/Users/private/run" not in repair_bytes
        provider = archive.extractfile("quarantine/attempt-1/provider-receipts.jsonl")
        assert provider is not None
        provider_bytes = provider.read()
        assert b"descript_quality_not_studio_sound" in provider_bytes
        assert b'"echo_score": 0.6483' in provider_bytes
        assert b"private-project" not in provider_bytes
        assert b"private-composition" not in provider_bytes
