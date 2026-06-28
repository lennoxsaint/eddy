# Eddy Context

Eddy is an agentic video editor context: raw creator footage goes in, quality-gated long-form and
Shorts outputs come out, with local media kept source-safe.

## Language

**Hook Playbook**:
Eddy's offline Shorts taste corpus used to score whether a candidate Short opens strongly enough.
_Avoid_: Runtime Supadata dependency, inspiration list

**Final Short**:
A vertical export that passed hook, source-lock, style-lock, caption, ending, silence, and decode gates.
_Avoid_: Clip, candidate, sample

**Proof-Gated Edit**:
An Eddy edit that may be called complete only after every required deterministic and configured quality gate passes.
_Avoid_: Best attempt, proxy, looks fine

**Edit Path**:
The user-visible route Eddy uses for editorial decisions while Eddy still owns source safety, rendering, QA, and receipts.
_Avoid_: Provider only, model choice

**Host-Agent Edit**:
An edit path where the current assistant session supplies structured editorial decisions from an Eddy packet, and Eddy compiles, renders, and gates the result.
_Avoid_: Codex-only mode, manual editor

**Route Fallback**:
A recorded switch from a stalled or failing edit path to the next allowed path without discarding source hashes, transcript cache, run directory, or receipts.
_Avoid_: Silent retry, hidden downgrade

**Source Lock**:
Proof that the Short renderer used the intended raw camera and screen inputs.
_Avoid_: Flattened long-form reuse, inferred provenance

**Style Lock**:
Proof that the approved Shorts geometry and caption language stayed stable during render.
_Avoid_: Aspect-ratio-only check, loose layout

**Studio Sound**:
Eddy's local heavy voice-enhancement quality gate for speech cleanup.
_Avoid_: FFmpeg-only loudness pass, basic EQ

**HyperFrames Frame Contract**:
The project-local `frame.md` motion design system that governs overlays before animation.
_Avoid_: Ad hoc ffmpeg boxes, one-off overlay

**Storyboard Proof**:
A static `storyboard.html` inspection surface that proves every planned motion frame before animation.
_Avoid_: Trusting the animated render first

## Relationships

- A **Hook Playbook** scores many candidate clips, but only quality-gated candidates become **Final Shorts**.
- A **Final Short** must have exactly one **Source Lock** and one **Style Lock** receipt.
- A **Proof-Gated Edit** may use one or more **Edit Path** attempts, but the edit is not complete until gates pass.
- A **Host-Agent Edit** is an **Edit Path**, not a replacement for Eddy's deterministic compiler or QA.
- A **Route Fallback** keeps one run history; it must not hide which **Edit Path** produced each decision.
- **Studio Sound** is an audio gate for both long-form videos and **Final Shorts** unless explicitly disabled for tests.
- A **HyperFrames Frame Contract** produces a **Storyboard Proof** before any motion graphic is composited.

## Example Dialogue

> **Dev:** "Can I render Shorts from the finished YouTube export?"
> **Domain expert:** "No. If separate camera and screen sources exist, the **Source Lock** must prove those raw sources were used."

> **Dev:** "The layout is 1080x1920, so is the Short done?"
> **Domain expert:** "No. It is only a **Final Short** after the hook, karaoke caption, ending, style, silence, and decode gates pass."

> **Dev:** "The model got stuck but the proxy is watchable. Is that a perfect edit?"
> **Domain expert:** "No. A **Proof-Gated Edit** is either gate-green or it returns exact blockers and route history."

## Flagged Ambiguities

- "Hook corpus" and "hook playbook" are the same concept; use **Hook Playbook**.
- "Studio Sound" means Eddy's local heavy speech enhancement gate unless a Descript project path is explicitly used.
- "Perfectly edited" means **Proof-Gated Edit**, not universal subjective perfection or a weak best-attempt proxy.
