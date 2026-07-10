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
4. Call `eddy_host_packet(job_id=...)`. Review every transcript chunk and resolve every Editorial
   Review Ledger item. Use its source hashes, typed retake variants, protected moments, proof assets,
   screen-proof candidates, motion requirements, and prior repair evidence to author `EditPlanV3`.
5. Call `eddy_host_submit(job_id=..., payload=<EditPlanV3>)`. Repair validation errors rather than
   bypassing them.
6. Call `eddy_finalize(job_id=...)`, poll with `eddy_job_status`, and return only final paths or exact
   blockers. Use `eddy_cancel_job` when the user cancels.

If MCP tools are unavailable, continue automatically through the equivalent CLI commands; do not
make the user restart the edit:

```bash
eddy options <source>
eddy edit <source>
eddy packet <job-id>
eddy submit <job-id> edit-plan.json
eddy finalize <job-id>
eddy status <job-id>
```

## Ordered edit

1. Ingest read-only sources, record before hashes, and detect dual-source versus talking-head mode.
   When top-level media exists, it is the exclusive source set; nested `runs/`, `eddy-runs/`,
   `work/`, `final/`, cache, and quarantine artifacts are never re-ingested as raw footage.
2. Transcribe to word-level timings and measure every audio silence above 0.8 seconds. Reuse only a
   transcript cache keyed by the immutable camera SHA-256 and receipt every cache hit or miss.
3. Build the Editorial Review Ledger. Review every chunk; resolve every repeat, reset loop, false
   start, unfinished clause, separated retake, and long gap. Keep the last complete clean take by
   default. Intentional repetition requires a recorded reason.
4. Hunt and rank three distinct proof-carrying hook angles.
5. Build one shared body edit. Keep the final clean take by default and preserve all protected beats.
6. Compile all body drops, non-selected retake variants, hook removals, and Short removals into
   explicit splices. Tighten gaps above 0.2s to 0.1s, preserve word-onset pre-roll, cap unprotected
   delivered gaps at 0.28s, and cap protected silence at 0.8s. Reuse one shared body receipt.
7. Apply real Descript Studio Sound to audio only. Require provider success, a changed project,
   private export provenance, duration parity, and a signal-changing **Effect-Survival Gate**. Keep
   echo and voice-texture scores as review diagnostics, not false promotion vetoes. If the effect did
   not survive an export, retry once through a fresh private render. A retryable provider failure gets
   up to three operational attempts with backoff; authentication and provenance faults fail
   immediately. Reuse a prior green Studio Sound result only when the exact pre-audio MP4 hash,
   cached output hash, private provenance, and effect-survival receipt validate. Re-transcribe and QA
   cache hits normally. Never silently substitute local processing.
8. Render HyperFrames-native hook/section motion from a project-local frame and storyboard contract.
   Place compact skeuomorphic panels against the real underlying frame, automatically choose the
   quietest valid region, reserve the camera PiP/face/caption/footer geometry, and prove the rendered
   overlay pixels stay inside their assigned regions before compositing.
9. Composite the full-frame screen and rounded camera treatment, or the talking-head layout.
10. Render quality-gated Shorts from source-locked camera/screen inputs with one-line karaoke.
    Project every caption word through the exact splice receipt and verify its timing against a fresh
    delivered transcript. A dual-source Short needs at least 25% verified raw-screen proof plus two
    compact animated HyperFrames beats: an opening hook beat by 2s and a later supporting proof beat.
11. Iterate with proxies; render full resolution only after the final plan is green.
12. Re-transcribe every emitted long and Short. Actual delivered silence is the hard pacing truth.
    If word timing shows sustained slow p95 cadence or an extreme gap above 0.8s, run up to three
    improving time-only repairs, re-transcribe after each pass, verify, then re-hash all sources.

## Hard gates

- Source hashes are identical before and after the run.
- Exactly one shared body plan feeds all three longs; only their hook segments differ.
- Every `keep` beat and protected span survives.
- Every delivered long and Short is retranscribed. No genuine retake, false start, reset loop, or
  unresolved repetition survives the delivered transcript. A deliberate callback is exempt only
  when its delivered variants match the exact source-ledger candidate reviewed as intentional.
- Word onsets are audible; gap, silence, loudness, clipping, and A/V drift gates pass.
- Descript duration parity and Effect-Survival Gate pass on the delivered audio.
- Screen/camera geometry, transcript-synchronous caption timing, proof assets, rendered contextual
  motion placement, Shorts source/style locks, 25% source-mapped screen proof, and motion activity at
  10 fps pass.
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
