---
description: Start a full Eddy edit (transcribe → edit loop → render → shorts → launch kit) on a footage path and report the result.
---

Start an Eddy edit for: **$ARGUMENTS**

Use the Eddy MCP tools (the run is asynchronous — a full edit takes 5–15 minutes):

1. Call `eddy_run_start` with `source` set to the footage path in $ARGUMENTS. If the user asked for a target length, pass `target_minutes`; for a fully on-device run pass `local_only=true`. Capture the returned `job_id` and `run_dir`.
2. Poll `eddy_job_status(job_id)` roughly every 30 seconds. Tell the user the current `phase` between polls — do not sit silent. Stop when `state` is `completed` or `failed`.
3. On `completed`: call `eddy_artifacts` with the run slug and summarise the launch kit — the candidate titles, the description, chapters, the shorts ledger, and the final video path.
4. On `failed`: surface the `log_tail` from the status payload so the user can see what broke.

Never publish or upload anything — Eddy only produces local files.
