import asyncio
import json
from pathlib import Path

import pytest

from eddy import cli, mcp_server, worker
from eddy.pipeline import PipelineRunner
from eddy.runtime import JobManager, JobState
from eddy.service import EddyService
from eddy.sync import check_projection, write_projection
from test_runtime import valid_plan


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


def test_cli_exposes_options_packet_submit_and_finalize(tmp_path: Path, capsys, monkeypatch) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({"schema_version": "edit-plan-v3"}))
    calls = []

    class FakeService:
        def edit_options(self, source, *, format="youtube", profile_id=None):
            calls.append(("options", source, format, profile_id))
            return {"requires_choice": False}

        def host_packet(self, job_id):
            calls.append(("packet", job_id))
            return {"job_id": job_id}

        def host_submit(self, job_id, payload):
            calls.append(("submit", job_id, payload))
            return {"state": "compiling"}

        def finalize(self, job_id):
            calls.append(("finalize", job_id))
            return {"worker": "started"}

        def opening_candidates(self, job_id):
            calls.append(("opening-candidates", job_id))
            return {"status": "auto_selected"}

        def select_opening(self, job_id, opening_id, *, reason):
            calls.append(("select-opening", job_id, opening_id, reason))
            return {"state": "compiling"}

        def repair_captions(self, job_id):
            calls.append(("repair-captions", job_id))
            return {"status": "pass"}

        def sync_doctor(self):
            return {}

    monkeypatch.setattr(cli, "_service", lambda _root: FakeService())

    assert cli.main(["options", "source-folder"]) == 0
    capsys.readouterr()
    assert cli.main(["packet", "job-1"]) == 0
    capsys.readouterr()
    assert cli.main(["submit", "job-1", str(plan_path)]) == 0
    capsys.readouterr()
    assert cli.main(["finalize", "job-1"]) == 0
    capsys.readouterr()
    assert cli.main(["opening-candidates", "job-1"]) == 0
    capsys.readouterr()
    assert cli.main(
        ["select-opening", "job-1", "opening-2", "--reason", "stronger proof"]
    ) == 0
    capsys.readouterr()
    assert cli.main(["repair-captions", "job-1"]) == 0
    capsys.readouterr()

    assert calls == [
        ("options", "source-folder", "youtube", None),
        ("packet", "job-1"),
        ("submit", "job-1", {"schema_version": "edit-plan-v3"}),
        ("finalize", "job-1"),
        ("opening-candidates", "job-1"),
        ("select-opening", "job-1", "opening-2", "stronger proof"),
        ("repair-captions", "job-1"),
    ]


def test_mcp_server_exposes_every_public_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDDY_RUNS_ROOT", str(tmp_path / "runs"))
    server = mcp_server.build_server()

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "eddy_edit_options",
        "eddy_edit_start",
        "eddy_capabilities",
        "eddy_host_packet",
        "eddy_host_submit",
        "eddy_opening_candidates",
        "eddy_select_opening",
        "eddy_finalize",
        "eddy_job_status",
        "eddy_cancel_job",
        "eddy_support_bundle",
        "eddy_sync_doctor",
        "eddy_record_feedback",
        "eddy_repair_privacy",
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


def test_worker_failure_quarantines_partial_attempt(tmp_path: Path, monkeypatch) -> None:
    runs = tmp_path / "runs"
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    manager = JobManager(runs)
    job = manager.start(source)
    attempt = job.run_dir / "work" / "attempt-1"
    attempt.mkdir(parents=True)
    (attempt / "partial.mp4").write_bytes(b"partial")

    def fail_finalize(self, job_id: str) -> None:
        raise RuntimeError("render_crashed")

    monkeypatch.setattr(PipelineRunner, "finalize", fail_finalize)
    result = worker.main(
        [
            "finalize",
            "--runs-root",
            str(runs),
            "--canonical-root",
            str(ROOT),
            "--job-id",
            job.id,
        ]
    )

    blocked = manager.load(job.id)
    assert result == 1
    assert blocked.state is JobState.BLOCKED
    assert "worker_failed:render_crashed" in blocked.blockers
    assert (job.run_dir / "quarantine" / "attempt-1" / "partial.mp4").exists()
    assert not attempt.exists()


def test_service_finalize_launches_worker_and_bundle_is_media_free(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)
    started = service.edit_start(str(source))
    job = service.manager.load(started["job_id"])
    lock = json.loads((job.run_dir / "source-lock.json").read_text())
    plan = valid_plan()
    plan["source_hashes"] = lock["before"]
    service.host_submit(job.id, plan)
    launched = []
    monkeypatch.setattr(service, "_launch_worker", lambda action, job_id: launched.append((action, job_id)))

    result = service.finalize(job.id)
    bundle = service.support_bundle(job.id)

    assert result["worker"] == "started"
    assert launched == [("finalize", job.id)]
    assert Path(bundle["bundle"]).exists()
    assert bundle["media_included"] is False

    with pytest.raises(RuntimeError, match="finalize_already_claimed"):
        service.finalize(job.id)


def test_job_payload_names_candidate_proof_state(tmp_path: Path) -> None:
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"raw")
    service = EddyService(tmp_path / "runs", auto_prepare=False)

    started = service.edit_start(str(source))

    assert started["proof_state"] == "candidate"
    assert started["owner_approved"] is False


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
