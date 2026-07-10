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

**Owner Channel**:
The maintainer installation channel linked directly to canonical `main`.
_Avoid_: Public latest, nightly release

**Stable Channel**:
The external installation channel that advances only to green immutable tags.
_Avoid_: Main, automatic development build

