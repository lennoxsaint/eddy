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
    def edit_options(source: str, format: str = "youtube") -> dict[str, Any]:
        return service.edit_options(source, format=format)

    @server.tool(name="eddy_edit_start")
    def edit_start(source: str, format: str = "youtube") -> dict[str, Any]:
        return service.edit_start(source, format=format)

    @server.tool(name="eddy_host_packet")
    def host_packet(job_id: str) -> dict[str, Any]:
        return service.host_packet(job_id)

    @server.tool(name="eddy_host_submit")
    def host_submit(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return service.host_submit(job_id, payload)

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

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
