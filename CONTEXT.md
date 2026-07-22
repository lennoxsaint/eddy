# Eddy Context

Eddy turns raw creator footage into source-safe, proof-gated video deliverables.

## Language

**Editorial Contract**:
The platform-neutral definition of what Eddy makes, protects, and requires before completion.
_Avoid_: Mega prompt, plugin instructions

**Platform Adapter**:
A thin Codex or Claude surface that exposes the Editorial Contract and Eddy's runtime controls.
_Avoid_: Separate Eddy skill, second implementation

**Installed Projection**:
A linked or generated copy of the canonical Eddy package used by an agent host.
_Avoid_: Source of truth, installed cache

**Primary Long**:
The highest-ranked complete long-form edit produced from the shared body and strongest hook angle.
_Avoid_: Default export, version one

**Alternate Long**:
A complete long-form edit that reuses the Primary Long's body but opens with a different ranked hook.
_Avoid_: Independent edit, draft

**Effect-Survival Gate**:
Provider success plus proof that Descript's returned audio contains a real signal-changing effect
while preserving timing. Echo and voice-texture heuristics remain diagnostics, not provider
classifiers or promotion vetoes.
_Avoid_: Successful API job alone, subjective quality oracle

**Proof-Gated Edit**:
An edit whose mandatory deterministic and configured quality gates are all green.
_Avoid_: Best attempt, rendered successfully

**Blocked Attempt**:
A playable inspection artifact quarantined with exact blockers after a required gate remains red.
_Avoid_: Final with warning, partial final

**Editorial Review Ledger**:
The stable, source-timed inventory of transcript chunks, exact and similar repeats, reset loops,
false starts, unfinished clauses, and every measured silence above 0.8 seconds. The host must review
every chunk and resolve every item before Eddy can compile an edit.
_Avoid_: Retake hints, model notes

**Protected Pause Ceiling**:
Protected content can retain its meaning, but protection never exempts more than 0.8 seconds of
silence. Longer silence is tightened and remains a blocking delivered-media finding if it survives.
_Avoid_: Sacred means untouched, unlimited intentional pause

**Screen Proof Beat**:
A source-mapped interval from the immutable raw screen recording that visibly proves the narrated
claim in the delivered Short.
_Avoid_: Generated proof card, decorative panel

**Animated Proof Beat**:
A HyperFrames beat with at least three distinct perceptual frame states at 10 fps and less than 80%
frozen time.
_Avoid_: Static overlay, title card

**Caption Timeline Truth**:
Short captions whose word timings are projected through the exact source-segment splice receipt and
then checked against a fresh transcript of the delivered Short. Synthetic per-word cadence is never
accepted as edited-timeline timing.
_Avoid_: Evenly spaced captions, source-time captions on an edited clip

**Contextual Motion Placement**:
Per-beat placement selected from the real underlying video frame, using the quietest valid region
while excluding the camera PiP, face, caption band, and delivery-safe footer. Promotion verifies the
rendered overlay pixels, not just the motion plan.
_Avoid_: Center everything, overlay-only collision proof

**Skeuomorphic Motion Panel**:
A compact animated panel that borrows the window chrome, light/dark treatment, depth, and scale of
the visible desktop environment while leaving the source proof legible around it.
_Avoid_: Full-screen title card, opaque proof replacement, giant text over UI

**Project Frame Contract**:
A run-local `frame.md` whose SHA-256 is bound into `edit-plan-v3.2` and newer; it records the visual thesis,
evidence order, layout grammar, and transition restraint before rendering.
_Avoid_: Unversioned style prompt, global brand guess

**Semantic Visual Choreography**:
A speech-anchored scene timeline where every meaningful change declares its job, evidence authority,
layout state, motion verb, transition, and cause. HyperFrames controls the whole composition.
_Avoid_: Decorative motion quota, small overlay list

**Opening Candidate Selection**:
Deterministic ranking of the three opening treatments. Eddy auto-selects only when the leader is
certain and more than five points clear; otherwise it pauses for a receipted host choice.
_Avoid_: Guessing the winner, rank-1 hook as implicit visual winner

**Shared-Body Composition Hash**:
The SHA-256 of the single HyperFrames body render reused by all three Longs.
_Avoid_: Three similar body renders, visual drift described as reuse

**Body Structure Contract**:
The hash-bound Sage route, body mode, ordered macro sections, proof-scene mapping, progress cues,
and final payoff consumed by `edit-plan-v3.3`.
_Avoid_: Editor outline, suggested chapters

**Macro Order Authority**:
The rule `sage_locked_eddy_may_not_reorder`: Eddy can tighten and visually improve a section but
cannot invent, remove, or reorder sections.
_Avoid_: Editorial discretion over the script spine, silent restructuring

**Evidence-Bearing Short**:
A dual-source Short with at least 25% real source-mapped screen proof, an animated hook beat in its
first two seconds, a later animated proof beat, transcript-synchronous captions, delivered-media
transcription, and green audio, contextual-motion, and editorial gates.
_Avoid_: Talking head plus static card, motion-only proof

**Exact Studio Sound Reuse**:
A content-addressed reuse of a previously green private Descript output only when the complete
pre-audio MP4 hash, cached output hash, provider provenance, and effect-survival proof all validate.
The delivered file is still re-transcribed and rechecked.
_Avoid_: Audio fallback, filename cache, assumed Studio Sound

**Privacy Mask**:
A deterministic, hook-scoped visual redaction rendered into the Long before Studio Sound and bound
to delivered-relative time plus a validated 1920x1080 rectangle. It protects incidental people or
private evidence without altering the immutable source files.
_Avoid_: Source mutation, editor-memory blur, approval-time redaction

**Short Privacy Repair**:
A post-completion, pixels-only Eddy repair that redacts an incidental Short exposure while preserving
every Long hash and the proven Studio Sound audio stream byte-for-byte.
_Avoid_: New audio render, Long replacement, unreceipted export

**Owner Channel**:
The maintainer installation channel linked directly to canonical `main`.
_Avoid_: Public latest, nightly release

**Stable Channel**:
The external installation channel that advances only to green immutable tags.
_Avoid_: Main, automatic development build
