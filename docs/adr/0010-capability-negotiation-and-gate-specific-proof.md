# ADR 0010: Capability negotiation and gate-specific proof

## Status

Accepted for owner-channel dogfood. The stable `v3.0.0` release remains unchanged.

## Decision

Eddy publishes `eddy-capabilities-v1`. Orchestrators negotiate schemas and route limits from that
declaration instead of hardcoding them. `edit-plan-v3.7` supports 3-6 named Long routes sharing one
body and 3-5 Shorts. Its Opening Blueprint is optional and never inferred from route count.

Professional promotion uses `professional-gate-evidence-v2` and `verifier-review-v2`. Every gate
has a distinct evaluator and a purpose-specific, hash-bound receipt. A single generic evidence file
cannot clear unrelated gates, and editor-authored prose cannot clear a detected defect. Cut review
uses source-mapped candidates, +/-8 boundary frames, decoder passthrough, and a 0.25x supercut.

## Compatibility

`edit-plan-v3.5`, `edit-plan-v3.6`, their host packets, and their proof contracts remain readable
and test-covered. No new stable tag is published until real-footage dogfood is owner-reviewed.
