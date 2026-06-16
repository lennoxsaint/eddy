"""Back-compat shim: the job manager moved to core `eddy.jobs` so the TUI can use it without the
optional `mcp` extra. Re-exported here so existing imports (and tests) keep working."""

from __future__ import annotations

from eddy.jobs import Job, JobManager, SpawnFn, _default_spawn, _flag3, _tail

__all__ = ["Job", "JobManager", "SpawnFn", "_default_spawn", "_flag3", "_tail"]
