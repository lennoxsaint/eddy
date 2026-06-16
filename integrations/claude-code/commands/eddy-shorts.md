---
description: Mine vertical shorts from a footage path (no full long-form edit).
---

Mine vertical shorts from: **$ARGUMENTS**

1. Call `eddy_shorts_start` with `source` set to the footage path in $ARGUMENTS. Capture the `job_id`.
2. Poll `eddy_job_status(job_id)` until `state` is `completed` (report `phase` between polls).
3. On completion, call `eddy_artifacts` with the run slug and report the shorts ledger (each short's hook + path).

This skips the long-form edit loop — it only produces the vertical clips. Never publish or upload.
