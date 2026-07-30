# ADR 0009: Pre-production opening blueprints bind delivered choreography

- Status: accepted
- Date: 2026-07-30

## Context

Eddy previously authored opening choreography after footage arrived. That preserved editorial
judgment, but it also allowed the pre-production hook intent to disappear between scripting and
post-production.

Strategy Profile V7 introduces a private, human-confirmed Opening Mechanics Library and a
per-episode Opening Edit Blueprint. The benchmark locks reusable editing functions rather than any
creator's visual identity.

## Decision

`edit-plan-v3.6` binds the exact Opening Edit Blueprint and Opening Mechanics Library refs and
hashes. Every planned scene through second 60 maps exactly once to a delivered scene. Its
communication job and evidence requirement are locked; styling remains flexible.

The thresholds remain exact: money shot by second 3, proof by second 10, route by second 30, and
8-12 meaningful visual changes in the first 30 seconds. Any changed treatment, reorder, or
replacement is explicit and evidence-backed. Missing scenes and unreceipted deviations fail before
render.

Legacy plans remain readable and reproducible, but cannot claim V7 delivered-opening proof.

## Consequences

- Editors receive executable cut intent before recording instead of decorating a finished talk.
- Pre-production and delivery can be compared deterministically.
- The benchmark can evolve through versioned libraries without silently changing active episodes.
- Creator identities, signature looks, and private clips never enter generated plugin projections.
