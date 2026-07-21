# ADR 0005: HyperFrames owns semantic visual choreography

Date: 2026-07-21

## Status

Accepted.

## Context

Eddy v3.1 proved opening deadlines and comparison surfaces, but its runtime still rendered compact
motion panels over a fixed camera/screen composite. The strongest recent edits used a different
grammar: real proof or an illustration could become the canvas; the speaker could move between full,
edge, PiP, circle, or absent states; and each transition was caused by a change in the argument.
Discovery hover previews also make frame one, second 3, and second 30 disproportionately important.

## Decision

`edit-plan-v3.2` adds a hash-bound project `frame.md` and four choreography surfaces: three opening
timelines, one shared-body timeline, and portrait timelines for every Short. Each scene declares its
timing, speech anchor, semantic job, meaningful change, layout, evidence authority, source refs,
motion verb, transition, cause, preview safety, and any justified quiet hold.

HyperFrames compiles each surface into one paused, seek-safe GSAP timeline. Camera and screen cut
masters remain synchronized and source-locked. The body is rendered once and reused. Real assets are
preferred over recreated proof. Opening candidates auto-rank, but Eddy pauses when the top two are
within five points or either leading judgment is uncertain.

## Consequences

- v3 and v3.1 remain backward compatible and keep their existing overlay path.
- v3.2 can change the actual visual layout rather than decorating a fixed composite.
- Opening cadence, layout diversity, transition restraint, and evidence provenance become schema
  gates instead of taste notes.
- A final candidate carries the frame hash, choreography manifests, animation maps, provenance,
  opening ranking/selection, shared-body hash, and 0/1/3/10/30 comparison frames.
