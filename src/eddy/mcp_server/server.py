"""FastMCP server exposing Eddy's tools over stdio — the `eddy-mcp` entry point.

Registers the plain functions from `tools.py` (FastMCP derives each tool's schema from the type hints
and its description from the docstring). Long operations are the ``*_start`` job tools paired with
``eddy_job_status`` / ``eddy_job_cancel``; everything else returns immediately.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from eddy.mcp_server import tools

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

_INSTRUCTIONS = (
    "Drive Eddy, a local-first agentic video editor. For the simple user promise — raw footage in, "
    "finished edit or exact blockers out — start with eddy_edit_start. For lower-level control, use "
    "eddy_run_start (it "
    "returns a job_id immediately); poll eddy_job_status(job_id) until state is 'completed', then "
    "read results with eddy_artifacts(run). Reads (eddy_runs, eddy_run_inspect, eddy_doctor, "
    "eddy_profiles, eddy_qa, eddy_pick, eddy_artifacts) return quickly (eddy_doctor may briefly probe "
    "a local Ollama). Jobs are tracked per server session; eddy_job_cancel works within the session "
    "that started the job. Destructive tools (eddy_clean, eddy_purge) require confirm=true."
)

# All tools exposed, grouped by kind. Single source of truth for registration and for tests.
TOOLS: list[Callable[..., Any]] = [
    # reads
    tools.eddy_doctor,
    tools.eddy_runs,
    tools.eddy_run_inspect,
    tools.eddy_profiles,
    tools.eddy_qa,
    tools.eddy_pick,
    tools.eddy_artifacts,
    # jobs
    tools.eddy_edit_start,
    tools.eddy_run_start,
    tools.eddy_shorts_start,
    tools.eddy_transcribe_start,
    tools.eddy_render_start,
    tools.eddy_batch_start,
    tools.eddy_job_status,
    tools.eddy_job_cancel,
    tools.eddy_jobs,
    # destructive (confirm-gated)
    tools.eddy_clean,
    tools.eddy_purge,
]


def build_server() -> FastMCP:
    """Construct the FastMCP app with every Eddy tool registered."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("eddy", instructions=_INSTRUCTIONS)
    for fn in TOOLS:
        mcp.tool()(fn)
    return mcp


def main() -> None:
    """Console entry point: run the server over stdio (what Claude Code / Codex / Desktop launch)."""
    build_server().run()


if __name__ == "__main__":
    main()
