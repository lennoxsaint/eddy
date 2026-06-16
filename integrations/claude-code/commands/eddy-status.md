---
description: Show recent Eddy runs and the status of any in-flight edit jobs.
---

Report Eddy's status.

1. Call `eddy_runs` for the fleet list (every run with its phase + best iteration).
2. Call `eddy_jobs` for any jobs this MCP session has started.
3. Summarise plainly: which runs are finished, which are mid-edit (with their `phase`), and any failures.

If the user named a specific run in **$ARGUMENTS**, call `eddy_run_inspect` with it and report that run's state and its `final/` artifacts in detail.
