# Eddy

Eddy is a skill-first, proof-gated YouTube editor. Give it raw camera footage and, when available,
a screen recording. It returns one ranked primary long, two complete alternate-hook longs sharing
the same body edit, and only genuinely strong Shorts.

Eddy never mutates source media and never publishes. A red render is quarantined as a Blocked
Attempt; it is never relabeled as final.

## Install channels

- **Owner development:** clone `main`, then run `python3 scripts/install_owner_surfaces.py` and
  `python3 scripts/install_owner_plugin.py`. Claude, Codex, and Agents skill folders become symlinks
  to the canonical checkout, while `eddy@personal` is refreshed from its generated V3 projection.
- **Public/plugin:** install a stable `vX.Y.Z` tag. Plugin bootstrap updates atomically and keeps the
  prior working tag if smoke checks fail.

Verify either channel with:

```bash
eddy sync-doctor
```

## Workflow

```text
eddy_edit_options -> eddy_edit_start -> awaiting_host_plan -> eddy_host_packet -> EditPlanV3.5|V3.6
-> eddy_host_submit -> auto-selected | awaiting_opening_selection -> eddy_finalize
-> awaiting_independent_review -> eddy_submit_review
-> proof_gated_candidate_awaiting_owner_taste | awaiting_host_repair | blocked
```

The CLI provides the same recovery path when MCP is unavailable:

```bash
eddy options <source>
eddy edit <source> [--profile-id <id>] [--project-brief project-fact-brief.json]
eddy packet <job-id>
eddy submit <job-id> edit-plan.json
eddy opening-candidates <job-id>
eddy select-opening <job-id> <opening-id> --reason "<evidence>"
eddy finalize <job-id>
eddy submit-review <job-id> verifier-submission.json
eddy repair-captions <job-id>
eddy repair-privacy <job-id> privacy-repair.json
eddy record-feedback <job-id> owner-verdict.json
```

Explicit owner feedback is stored beside the run and classified before it becomes product doctrine.
Generalizable changes ship with `scripts/ship_to_github.py`, which refuses unrelated changes and
updates projections, GitHub `main`, CI proof, and the installed owner plugin as one guarded action.

The host model owns editorial taste. Eddy owns source locks, deterministic media mechanics,
asynchronous state, receipts, cancellation, and proof gates. Read [SKILL.md](SKILL.md) for the full
product contract.

Strategy Profile V7 projects use `edit-plan-v3.6`; projects without a V7 Opening Edit Blueprint
remain on `edit-plan-v3.5`. V3.6 retains v3.5's proof system and adds an exact delivered-opening map.
The pre-production Opening Edit Blueprint binds every scene
through second 60; each scene keeps its communication job and evidence requirement, while the
editor remains free to adapt style to the footage. Threshold drift, missing scenes, and unreceipted
deviations fail before render.

V3.6 also retains v3.2's opening choreography and v3.3's hash-bound, Sage-owned body spine, then
binds the Lennox v2 profile, Project Fact Brief, design contracts,
sample-exact cut policy, Studio Sound lineage, independent verifier, and correction evals. A route
understood by second 30 resolves through 3-5 ordered sections; Eddy
maps every body scene to those sections and cannot silently reorder them. A hash-bound `frame.md`
still drives three opening compositions, one reused shared-body composition, and portrait Short
timelines. HyperFrames controls full-frame proof, speaker geometry, illustrations, and semantically
motivated transitions instead of merely adding small overlays.

Preflight writes an Editorial Review Ledger. Final verification retranscribes every emitted video;
waveform evidence controls when transcript timing conflicts, and source-plan timing never
substitutes for delivered-media proof. Passing objective evidence stops at the owner taste lock.

If the source folder contains top-level media, Eddy locks only those files. Nested prior run outputs
are excluded, preventing an old `eddy-runs/` folder from being mistaken for fresh camera or screen
footage. Quality transcripts are cached only by the camera SHA-256 and every reuse is receipted.

## v3.0 boundary

Included: three long variants, quality-gated Shorts, transcript, edit plan, spot checks, QA, and
receipts.

Excluded: titles, descriptions, chapters, thumbnails, uploading, publishing, sending, scheduling,
and non-Descript audio fallbacks.

Eddy may claim "safe to publish without human review" only after five diverse owner-approved
dogfood runs are recorded green in `dogfood/trust-ledger.json`.
