import asyncio
import json
from pathlib import Path

from eddy import cli, mcp_server, worker
from eddy.pipeline import PipelineRunner
from eddy.runtime import JobManager, JobState
from eddy.service import EddyService
from eddy.sync import check_projection, write_projection


ROOT = Path(__file__).resolve().parents[1]


def test_cli_sync_doctor_emits_json(tmp_path: Path, capsys) -> None:
    result = cli.main(["--runs-root", str(tmp_path / "runs"), "sync-doctor"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["product"] == "Eddy"


def test_cli_returns_exact_blocker_for_missing_source(tmp_path: Path, capsys) -> None:
    result = cli.main(["--runs-root", str(tmp_path / "runs"), "edit", str(tmp_path / "missing")])

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert "source_not_found" in payload["blocker"]


def test_mcp_server_exposes_every_public_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDDY_RUNS_ROOT", str(tmp_path / "runs"))
    server = mcp_server.build_server()

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "eddy_edit_options",
        "eddy_edit_start",
        "eddy_host_packet",
        "eddy_host_submit",
        "eddy_finalize",
        "eddy_job_status",
        "eddy_cancel_job",
        "eddy_support_bundle",
        "eddy_sync_doctor",
    } <= names


def test_worker_prepare_uses_pipeline_runner(tmp_path: Path, monkeypatch) -> None:
    runs = tmp_path / "runs"
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    manager = JobManager(runs)
    job = manager.start(source)

    def fake_prepare(self, job_id: str) -> None:
        self.manager.transition(job_id, JobState.AWAITING_HOST_PLAN)

    monkeypatch.setattr(PipelineRunner, "prepare", fake_prepare)
    result = worker.main(
        [
            "prepare",
            "--runs-root",
            str(runs),
            "--canonical-root",
            str(ROOT),
            "--job-id",
            job.id,
        ]
    )

    assert result == 0
    assert manager.load(job.id).state is JobState.AWAITING_HOST_PLAN


def test_service_finalize_launches_worker_and_bundle_is_media_free(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)
    started = service.edit_start(str(source))
    job = service.manager.load(started["job_id"])
    lock = json.loads((job.run_dir / "source-lock.json").read_text())
    plan = {
        "schema_version": "edit-plan-v3",
        "source_hashes": lock["before"],
        "protected": [],
        "body": {"keep": [[0.0, 1.0]], "drop": [], "retake_groups": []},
        "hooks": [
            {"id": "a", "rank": 1, "segments": [[1.0, 2.0]], "proof_assets": []},
            {"id": "b", "rank": 2, "segments": [[2.0, 3.0]], "proof_assets": []},
            {"id": "c", "rank": 3, "segments": [[3.0, 4.0]], "proof_assets": []},
        ],
        "shorts": [],
        "motion_beats": [],
    }
    service.host_submit(job.id, plan)
    launched = []
    monkeypatch.setattr(service, "_launch_worker", lambda action, job_id: launched.append((action, job_id)))

    result = service.finalize(job.id)
    bundle = service.support_bundle(job.id)

    assert result["worker"] == "started"
    assert launched == [("finalize", job.id)]
    assert Path(bundle["bundle"]).exists()
    assert bundle["media_included"] is False


def test_write_projection_creates_a_matching_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    projection = tmp_path / "projection"
    source.mkdir()
    (source / "SKILL.md").write_text("canonical\n")

    manifest = write_projection(
        source,
        projection,
        canonical_commit="abc123",
        files=("SKILL.md",),
    )

    assert json.loads(manifest.read_text())["canonical_commit"] == "abc123"
    assert check_projection(source, projection, files=("SKILL.md",)).ok is True
