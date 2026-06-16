"""SDK handshake: build the FastMCP server and prove every tool registers with a usable schema.
If a tool signature were unsupported by the SDK, registration or list_tools would fail here."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")  # the server is an optional extra

from eddy.mcp_server.server import TOOLS, build_server  # noqa: E402


def _tools():
    return asyncio.run(build_server().list_tools())


def test_every_tool_registers():
    listed = _tools()
    assert len(listed) == len(TOOLS)
    names = {t.name for t in listed}
    assert names == {fn.__name__ for fn in TOOLS}


def test_core_tools_present():
    names = {t.name for t in _tools()}
    for expected in ("eddy_run_start", "eddy_job_status", "eddy_artifacts", "eddy_clean", "eddy_purge", "eddy_doctor"):
        assert expected in names


def test_tools_have_descriptions_and_schemas():
    for t in _tools():
        assert t.description, f"{t.name} has no description"
        assert t.inputSchema.get("type") == "object"


def test_run_start_schema_exposes_key_params():
    rs = next(t for t in _tools() if t.name == "eddy_run_start")
    props = rs.inputSchema.get("properties", {})
    assert "source" in props and "local_only" in props and "target_minutes" in props


def test_destructive_tools_expose_confirm():
    listed = {t.name: t for t in _tools()}
    assert "confirm" in listed["eddy_clean"].inputSchema["properties"]
    assert "confirm" in listed["eddy_purge"].inputSchema["properties"]
