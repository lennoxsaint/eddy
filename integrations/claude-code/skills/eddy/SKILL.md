---
name: eddy
description: >-
  Use Eddy to turn attached raw footage into a proof-gated YouTube primary long, two alternate-hook
  longs sharing the same body, and only genuinely strong Shorts. Eddy never publishes or mutates
  source media.
metadata:
  version: 3.0.0
  author: lennoxsaint
---

# Eddy

Use this skill when the user mentions Eddy, attaches raw footage, or asks for a YouTube edit. Call
the product **Eddy** in normal conversation; plugin namespaces and version labels are routing details.

The host model is Eddy's editorial brain. Eddy's thin runtime owns source locks, asynchronous stage
execution, deterministic mechanics, receipts, cancellation, and proof gates.

## Product contract

For a normal "edit this" request, Eddy produces videos only:

- one ranked primary long;
- two complete alternate-hook longs that reuse the identical body edit;
- 3-5 Shorts only when that many standalone moments pass every required gate;
- transcript, edit plan, spot checks, deterministic QA, and receipts.

Titles, descriptions, chapters, thumbnails, uploads, publishing, sending, and scheduling are outside
v3.0. Never mutate, move, delete, upload, or publish source media.

The hook carries roughly 90% of the video's leverage. Spend disproportionate editorial effort on the
first 30-60 seconds. Each hook must be self-contained, pay off a distinct angle, and show concrete
proof on screen when the narration names an artifact. Rank one angle as primary; the other two are
alternate hooks, not independently drifting body edits.

Preserve every unique substantive beat. Never gut a long recording into a summary clip, remove a
protected or vulnerable moment, regenerate speech, overdub the speaker, or rewrite the opening line.
Remove genuine retakes with last-take bias, remove dead air, and tighten ordinary gaps without
clipping word onsets or compressing protected pauses.

## Proof states

A **Proof-Gated Edit** has every mandatory deterministic and configured quality gate green. Only this
state may populate `final/` or be described as complete.

A **Blocked Attempt** is a playable inspection artifact with exact blockers and receipts. After at
most three repair attempts, keep the best red attempt under `quarantine/attempt-<n>/`; never promote
it into `final/` or call it ship-ready.

Do not claim Eddy is safe to publish without human review until the repository trust ledger records
five owner-approved dogfood runs with no unresolved critical failures. Before that unlock, call green
outputs proof-gated candidates.

## Default workflow

1. Resolve the attached local file or folder. If it cannot be resolved, stop with
   `attached_source_unresolved`; never guess.
2. Call `eddy_edit_options(source=<path>, format="youtube")`. If there is one runnable path, start it
   without asking. If a material route choice remains, show only runnable options with privacy, cost,
   and quality tradeoffs.
3. Call `eddy_edit_start(...)`, then poll until `awaiting_host_plan`.
4. Call `eddy_host_packet(job_id=...)`. Use its transcript, source hashes, retake groups, protected
   moments, proof assets, and Shorts candidates to author `EditPlanV3`.
5. Call `eddy_host_submit(job_id=..., payload=<EditPlanV3>)`. Repair validation errors rather than
   bypassing them.
6. Call `eddy_finalize(job_id=...)`, poll with `eddy_job_status`, and return only final paths or exact
   blockers. Use `eddy_cancel_job` when the user cancels.

## Ordered edit

1. Ingest read-only sources, record before hashes, and detect dual-source versus talking-head mode.
2. Transcribe to word-level timings.
3. Build a beat map covering every unique beat, protected span, retake group, and proof asset.
4. Hunt and rank three distinct proof-carrying hook angles.
5. Build one shared body edit. Keep the final clean take by default and preserve all protected beats.
6. Tighten ordinary gaps and remove energy-confirmed dead air using one shared segment receipt for
   camera and screen sources.
7. Apply real Descript Studio Sound to audio only. API success and duration parity are insufficient:
   the local returned artifact must pass the calibrated **Effect-Survival Gate**. If the effect did
   not survive export, block with `descript_effect_not_rendered`; do not silently fall back.
8. Render HyperFrames-native hook/section motion from a project-local frame and storyboard contract.
   Prove semantic collision safety before compositing.
9. Composite the full-frame screen and rounded camera treatment, or the talking-head layout.
10. Render quality-gated Shorts from source-locked camera/screen inputs with one-line karaoke.
11. Iterate with proxies; render full resolution only after the final plan is green.
12. Re-transcribe and verify every emitted long and Short, then re-hash all source files.

## Hard gates

- Source hashes are identical before and after the run.
- Exactly one shared body plan feeds all three longs; only their hook segments differ.
- Every `keep` beat and protected span survives.
- No genuine retake, false start, or reset loop survives the rendered transcript.
- Word onsets are audible; gap, silence, loudness, clipping, and A/V drift gates pass.
- Descript duration parity and Effect-Survival Gate pass on the delivered audio.
- Screen/camera geometry, captions, proof assets, motion collisions, and Shorts source/style locks pass.
- `spot-check.md`, `edit-plan.json`, `final/qa.json`, and `receipts.jsonl` are inspectable.

## Descript boundary

Descript is an audio service, not Eddy's editorial brain. Use either the direct API adapter or the
optional authenticated host plugin. Both must return a local audio artifact plus private-project,
composition, provider, and hash receipts, and both pass the same Effect-Survival Gate. Never expose
credentials in receipts, logs, project files, or answers.

Configure a host adapter with `EDDY_DESCRIPT_CONNECTOR`. Eddy passes `--input-wav`,
`--output-audio`, and `--receipt`. The receipt must identify `descript_host_connector`, a private
project and composition, and matching source/output SHA-256 hashes. The host owns authentication
and must not print credentials.

## Outputs

Successful runs write `final/long-primary.mp4`, two `final/long-alternate-<angle>.mp4` files,
`final/shorts/`, `final/transcript.md`, `final/qa.json`, `edit-plan.json`, `spot-check.md`, and
`receipts.jsonl`. Blocked runs return the exact blocker, quarantine path, and smallest repair action.
