"""The Eddy MCP server — drive Eddy from Claude Code, Codex, and Claude Desktop.

Hybrid by design: long, mutating operations (run, batch, shorts-mine, transcribe, render) run as
**subprocess jobs** (the real `eddy` CLI, fire-and-poll) so a 5-15 minute edit never blocks a tool
call and each run gets its own process — isolating Eddy's process-global egress/offline state and
reusing the hardened CLI path. Cheap reads (doctor, runs, status, profiles, pick, qa, artifacts) run
in-process for snappy structured returns. Transport is stdio (what all three clients launch).

Nothing here publishes or uploads; destructive tools (clean, purge) refuse without ``confirm=true``.
"""

from __future__ import annotations
