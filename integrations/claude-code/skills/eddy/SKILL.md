---
name: eddy
description: Use when the user wants to turn raw video footage into a finished YouTube launch kit (a long-form edit plus vertical shorts, titles, description, chapters, and thumbnails) with Eddy, the local-first agentic video editor. Covers starting and monitoring edits, mining shorts, inspecting runs, and reading results through the eddy-mcp tools.
---

# Driving Eddy

Eddy turns raw footage into a complete launch kit, entirely on the user's machine. You drive it through the `eddy-mcp` MCP tools. Eddy never publishes or uploads — it only writes local files under the run directory.

## Long operations are jobs (start → poll → read)

A full edit takes 5–15 minutes, so the long tools are asynchronous. Never block on them:

1. **Start** — `eddy_run_start(source, target_minutes?, local_only?, format?, language?, profile?)` returns `{ job_id, run_dir }` immediately. The `job_id` is the run's slug.
2. **Poll** — `eddy_job_status(job_id)` returns `running | completed | failed | interrupted` plus the current `phase` (transcribe, iteration_N, final_render, shorts, package, done). Poll every ~30s and keep the user informed; on `failed` the payload includes a `log_tail`.
3. **Read** — `eddy_artifacts(run)` returns the candidate titles, description, chapters, shorts ledger, and the final video path. `eddy_run_inspect(run)` returns raw run state + a `final/` inventory.

The same start→poll→read pattern applies to `eddy_shorts_start` (vertical clips only, no long edit), `eddy_transcribe_start`, `eddy_render_start`, and `eddy_batch_start` (a directory of sources).

## Instant reads (no job)

- `eddy_runs` — every run with phase + best iteration.
- `eddy_run_inspect(run)` — one run's state and artifact inventory.
- `eddy_doctor` — hardware + provider detection and an environment preflight.
- `eddy_profiles` — configured per-channel run profiles.
- `eddy_qa(run, iteration?)` — deterministic QA (+ judge if a proxy exists).
- `eddy_pick(run)` — deterministic A/B title + thumbnail pick.

## Rules

- **Never publish or upload.** Eddy produces local files only; uploading is out of scope.
- **Destructive tools need confirmation.** `eddy_clean` (reclaims scratch) and `eddy_purge` (deletes PII; `full=true` erases the whole run) refuse unless `confirm=true`. Always confirm with the user first; `eddy_purge` is irreversible.
- **On-device runs** — pass `local_only=true` to keep everything on the machine (no cloud brain, no model downloads, no cloud thumbnail APIs).
- **Identify a run by its slug** (the run directory name); use it as both `job_id` and `run`.
- **Tutorials/lessons** — pass `format="tutorial"` (or lesson/longform/podcast) to lift the length ceiling.
