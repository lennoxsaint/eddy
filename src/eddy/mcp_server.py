"""MCP projection of EddyService. Import remains optional for base installs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .service import EddyService


def _service() -> EddyService:
    root = Path(os.environ.get("EDDY_RUNS_ROOT", Path.home() / ".eddy" / "runs"))
    return EddyService(root)


def build_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("mcp_extra_not_installed") from exc

    server = FastMCP("Eddy")
    service = _service()

    @server.tool(name="eddy_edit_options")
    def edit_options(
        source: str,
        format: str = "youtube",
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        return service.edit_options(source, format=format, profile_id=profile_id)

    @server.tool(name="eddy_edit_start")
    def edit_start(
        source: str,
        format: str = "youtube",
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        return service.edit_start(source, format=format, profile_id=profile_id)

    @server.tool(name="eddy_host_packet")
    def host_packet(job_id: str) -> dict[str, Any]:
        return service.host_packet(job_id)

    @server.tool(name="eddy_host_submit")
    def host_submit(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return service.host_submit(job_id, payload)

    @server.tool(name="eddy_opening_candidates")
    def opening_candidates(job_id: str) -> dict[str, Any]:
        return service.opening_candidates(job_id)

    @server.tool(name="eddy_select_opening")
    def select_opening(job_id: str, opening_id: str, reason: str) -> dict[str, Any]:
        return service.select_opening(job_id, opening_id, reason=reason)

    @server.tool(name="eddy_finalize")
    def finalize(job_id: str) -> dict[str, Any]:
        return service.finalize(job_id)

    @server.tool(name="eddy_job_status")
    def job_status(job_id: str) -> dict[str, Any]:
        return service.job_status(job_id)

    @server.tool(name="eddy_cancel_job")
    def cancel_job(job_id: str) -> dict[str, Any]:
        return service.cancel_job(job_id)

    @server.tool(name="eddy_support_bundle")
    def support_bundle(job_id: str, output: str | None = None) -> dict[str, Any]:
        return service.support_bundle(job_id, output)

    @server.tool(name="eddy_sync_doctor")
    def sync_doctor() -> dict[str, Any]:
        return service.sync_doctor()

    @server.tool(name="eddy_record_feedback")
    def record_feedback(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return service.record_feedback(job_id, payload)

    @server.tool(name="eddy_repair_privacy")
    def repair_privacy(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return service.repair_privacy(job_id, payload)

    @server.tool(name="eddy_revise_design_contracts")
    def revise_design_contracts(
        job_id: str,
        reason: str,
        design_markdown: str | None = None,
        long_frame_markdown: str | None = None,
        short_frame_markdown: str | None = None,
    ) -> dict[str, Any]:
        return service.revise_design_contracts(
            job_id,
            reason=reason,
            design_markdown=design_markdown,
            long_frame_markdown=long_frame_markdown,
            short_frame_markdown=short_frame_markdown,
        )

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
