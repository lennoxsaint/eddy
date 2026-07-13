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
eddy_edit_options -> eddy_edit_start -> awaiting_host_plan -> eddy_host_packet -> EditPlanV3
-> eddy_host_submit -> eddy_finalize -> completed | awaiting_host_repair | blocked
```

The CLI provides the same recovery path when MCP is unavailable:

```bash
eddy options <source>
eddy edit <source>
eddy packet <job-id>
eddy submit <job-id> edit-plan.json
eddy finalize <job-id>
eddy repair-captions <job-id>
eddy repair-privacy <job-id> privacy-repair.json
eddy record-feedback <job-id> owner-feedback.json
```

Explicit owner feedback is stored beside the run and classified before it becomes product doctrine.
Generalizable changes ship with `scripts/ship_to_github.py`, which refuses unrelated changes and
updates projections, GitHub `main`, CI proof, and the installed owner plugin as one guarded action.

The host model owns editorial taste. Eddy owns source locks, deterministic media mechanics,
asynchronous state, receipts, cancellation, and proof gates. Read [SKILL.md](SKILL.md) for the full
product contract.

Preflight writes an Editorial Review Ledger. Final verification retranscribes every emitted video;
source-plan timing never substitutes for delivered-media proof.

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
