# ADR 0006: Sage owns macro body order

- Status: Accepted
- Date: 2026-07-22

## Context

Eddy v3.2 could choreograph one shared body but had no machine-readable relationship to the route
promised in the script opening. An editor could produce a visually valid timeline while losing,
duplicating, or reordering the viewer's progress landmarks.

## Decision

`edit-plan-v3.3` requires `eddy-body-structure-v1`. The contract hash-binds the pre-production body
structure, preserves its mode and ordered section IDs, and maps every shared-body scene exactly once.
Every section names one or more proof scenes. Every non-final boundary maps to a reset scene with a
transition card and spoken callback.

The authority token is fixed to `sage_locked_eddy_may_not_reorder`. Eddy may remove dead air,
tighten gaps, select layouts, and improve pacing inside a section. It may block a broken spine, but
cannot create, remove, or reorder macro sections.

`edit-plan-v3.1` and `edit-plan-v3.2` remain readable without the new field. The current writer is
v3.3; no legacy plan is rewritten.

## Consequences

- The hook promise, script body, and visual edit share stable IDs.
- Silent editorial restructuring becomes a deterministic blocker.
- v3.3 hosts must supply a pre-production contract ref and hash.
- Existing projects retain playback and inspection compatibility.
