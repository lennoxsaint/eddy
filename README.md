# Eddy

Eddy is a skill-first, proof-gated YouTube editor. Give it raw camera footage and, when available,
a screen recording. It returns one ranked primary long, two complete alternate-hook longs sharing
the same body edit, and only genuinely strong Shorts.

Eddy never mutates source media and never publishes. A red render is quarantined as a Blocked
Attempt; it is never relabeled as final.

## Install channels

- **Owner development:** clone `main`, then run `python3 scripts/install_owner_surfaces.py`. Claude,
  Codex, and Agents skill folders become symlinks to the canonical checkout.
- **Public/plugin:** install a stable `vX.Y.Z` tag. Plugin bootstrap updates atomically and keeps the
  prior working tag if smoke checks fail.

Verify either channel with:

```bash
eddy sync-doctor
```

## Workflow

```text
eddy_edit_start -> awaiting_host_plan -> eddy_host_packet -> EditPlanV3
-> eddy_host_submit -> eddy_finalize -> completed | blocked
```

The host model owns editorial taste. Eddy owns source locks, deterministic media mechanics,
asynchronous state, receipts, cancellation, and proof gates. Read [SKILL.md](SKILL.md) for the full
product contract.

## v3.0 boundary

Included: three long variants, quality-gated Shorts, transcript, edit plan, spot checks, QA, and
receipts.

Excluded: titles, descriptions, chapters, thumbnails, uploading, publishing, sending, scheduling,
and non-Descript audio fallbacks.

Eddy may claim "safe to publish without human review" only after five diverse owner-approved
dogfood runs are recorded green in `dogfood/trust-ledger.json`.
