"""Generic host-agent edit packets.

The current MCP host (Codex Desktop, Claude Code, or another capable assistant) can make editorial
decisions from transcript/QA context while Eddy keeps media handling, compile, render, QA, receipts,
and exact blockers in the engine.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from eddy.config import load_config
from eddy.edit.compiler import CompileError, compile_edl
from eddy.edit.simulate import simulate
from eddy.edit.schema import EditDecisions, save
from eddy.loop.receipts import Receipts
from eddy.media.probe import duration_s
from eddy.transcribe.pack import audio_silence_map, phrases as load_phrases
from eddy.transcribe.whisper import words_flat

_MAX_PACKET_TEXT = 60_000


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path, limit: int = _MAX_PACKET_TEXT) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="replace")[:limit]


def _latest_iteration(run_dir: Path) -> Path | None:
    iterations = sorted((run_dir / "iterations").glob("[0-9][0-9]"))
    return iterations[-1] if iterations else None


def _next_iteration(run_dir: Path) -> Path:
    iterations = sorted((run_dir / "iterations").glob("[0-9][0-9]"))
    next_n = (int(iterations[-1].name) + 1) if iterations else 1
    path = run_dir / "iterations" / f"{next_n:02d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def host_packet(run_dir: Path | str) -> dict[str, Any]:
    """Build a bounded host-agent packet. It returns text/metadata only, never media bytes."""

    rd = Path(run_dir).expanduser()
    receipts = Receipts(rd)
    manifest = _read_json(rd / "manifest.json") or {}
    latest = _latest_iteration(rd)
    packet: dict[str, Any] = {
        "status": "ready" if (rd / "transcript" / "takes_packed.md").exists() else "needs_transcript",
        "run_dir": str(rd),
        "instructions": (
            "Return an EditDecisions JSON object. Eddy will validate it, compile it through the "
            "normal deterministic compiler, render locally, and pass/fail the result by Eddy QA gates."
        ),
        "schema": "EditDecisions",
        "media_policy": "No media bytes are included in this packet.",
        "source_hashes": manifest.get("source_sha256", {}),
        "sources": {
            key: {"path": str(path), "bytes_included": False}
            for key, path in (manifest.get("sources") or {}).items()
        },
        "transcript": {
            "path": str(rd / "transcript" / "takes_packed.md"),
            "excerpt": _read_text(rd / "transcript" / "takes_packed.md"),
        },
        "qa_context": {},
        "artifacts": {
            "words_json": str(rd / "transcript" / "words.json"),
            "phrases_json": str(rd / "transcript" / "phrases.json"),
        },
    }
    if latest is not None:
        packet["qa_context"]["latest_iteration"] = latest.name
        for name in ("qa.json", "judge.json", "directive.json", "sim.json"):
            data = _read_json(latest / name)
            if data is not None:
                packet["qa_context"][name.removesuffix(".json")] = data
    final_qa = _read_json(rd / "final" / "qa-final.json")
    if final_qa is not None:
        packet["qa_context"]["final_qa"] = final_qa
    receipts.log(
        "host_agent_packet",
        status=packet["status"],
        transcript_chars=len(packet["transcript"]["excerpt"]),
        media_bytes_included=False,
    )
    return packet


def _payload_to_decisions(payload: dict[str, Any]) -> EditDecisions:
    body = payload.get("decisions") if isinstance(payload.get("decisions"), dict) else payload
    return EditDecisions.model_validate(body)


def submit_host_decisions(run_dir: Path | str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and compile a host-agent EditDecisions payload.

    Invalid host payloads are exact blockers. Valid payloads are written to disk and compiled through
    Eddy's normal compiler when transcript/source context is present.
    """

    rd = Path(run_dir).expanduser()
    receipts = Receipts(rd)
    try:
        decisions = _payload_to_decisions(payload)
    except ValidationError as exc:
        blocker: dict[str, Any] = {
            "code": "invalid_host_decisions",
            "message": "The host assistant did not return a valid EditDecisions payload.",
            "fix": "Submit JSON that matches Eddy's EditDecisions schema.",
            "evidence": exc.errors(include_url=False)[:8],
        }
        receipts.log("host_agent_submit_blocked", blocker=blocker)
        return {"status": "blocked", "blockers": [blocker], "run_dir": str(rd)}

    host_dir = rd / "host-agent"
    host_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    decisions_path = host_dir / f"edit-decisions-{stamp}.json"
    save(decisions, decisions_path)

    words_path = rd / "transcript" / "words.json"
    manifest_path = rd / "manifest.json"
    if not words_path.exists() or not manifest_path.exists():
        blocker = {
            "code": "host_compile_context_missing",
            "message": "The host decisions were valid, but Eddy cannot compile them before transcription/source context exists.",
            "fix": "Run transcription first, then call eddy_host_packet and eddy_host_submit again.",
            "evidence": {"words_json": words_path.exists(), "manifest_json": manifest_path.exists()},
        }
        receipts.log("host_agent_submit_blocked", blocker=blocker, decisions_path=str(decisions_path))
        return {"status": "blocked", "blockers": [blocker], "decisions_path": str(decisions_path), "run_dir": str(rd)}

    manifest = json.loads(manifest_path.read_text())
    source_path = manifest.get("sources", {}).get("camera")
    if not source_path:
        blocker = {
            "code": "host_compile_source_missing",
            "message": "The run manifest does not identify a camera source for compilation.",
            "fix": "Open a normal Eddy run directory with a valid manifest, then retry.",
            "evidence": {"manifest": str(manifest_path)},
        }
        receipts.log("host_agent_submit_blocked", blocker=blocker, decisions_path=str(decisions_path))
        return {"status": "blocked", "blockers": [blocker], "decisions_path": str(decisions_path), "run_dir": str(rd)}

    cfg = load_config()
    phrases = load_phrases(rd)
    try:
        edl = compile_edl(
            decisions,
            words_flat(rd),
            str(source_path),
            duration_s(Path(source_path)),
            cfg.render,
            cfg.gates,
            silence_spans=audio_silence_map(rd),
            phrases=phrases,
            extract=decisions.x_eddy.focus_mode == "extract",
        )
    except CompileError as exc:
        blocker = {
            "code": "host_decisions_compile_failed",
            "message": "The host decisions were valid JSON but failed Eddy's deterministic compiler.",
            "fix": "Repair the listed intervals and submit a corrected EditDecisions payload.",
            "evidence": exc.problems,
        }
        receipts.log("host_agent_submit_blocked", blocker=blocker, decisions_path=str(decisions_path))
        return {"status": "blocked", "blockers": [blocker], "decisions_path": str(decisions_path), "run_dir": str(rd)}

    manifest_sources = manifest.get("sources") or {}
    if manifest_sources:
        edl.sources = {str(key): str(value) for key, value in manifest_sources.items() if value}
        edl.sources["camera"] = str(source_path)

    sim_report = simulate(
        edl,
        decisions,
        phrases,
        cfg,
        decisions.target_runtime_seconds or edl.total_duration_s,
    )
    edl_path = host_dir / f"edl-{stamp}.json"
    save(edl, edl_path)
    iter_dir = _next_iteration(rd)
    save(decisions, iter_dir / "edit-decisions.json")
    save(edl, iter_dir / "edl.json")
    (iter_dir / "sim-report.json").write_text(json.dumps(sim_report, indent=1))
    receipts.log(
        "host_agent_submit",
        decisions_path=str(decisions_path),
        edl_path=str(edl_path),
        iteration_dir=str(iter_dir),
        ranges=len(edl.ranges),
        duration_s=edl.total_duration_s,
        sim_pass=sim_report.get("pass"),
    )
    return {
        "status": "compiled",
        "run_dir": str(rd),
        "decisions_path": str(decisions_path),
        "edl_path": str(edl_path),
        "iteration_dir": str(iter_dir),
        "ranges": len(edl.ranges),
        "duration_s": edl.total_duration_s,
    }
