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
Proof that Descript's returned audio contains a real applied effect while preserving timing.
_Avoid_: Successful API job, duration parity

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

**Evidence-Bearing Short**:
A dual-source Short with at least 25% real source-mapped screen proof, an animated hook beat in its
first two seconds, a later animated proof beat, delivered-media transcription, and green audio and
editorial gates.
_Avoid_: Talking head plus static card, motion-only proof

**Owner Channel**:
The maintainer installation channel linked directly to canonical `main`.
_Avoid_: Public latest, nightly release

**Stable Channel**:
The external installation channel that advances only to green immutable tags.
_Avoid_: Main, automatic development build
