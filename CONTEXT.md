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
- **Studio Sound** is an audio gate for both long-form videos and **Final Shorts** unless explicitly disabled for tests.
- A **HyperFrames Frame Contract** produces a **Storyboard Proof** before any motion graphic is composited.

## Example Dialogue

> **Dev:** "Can I render Shorts from the finished YouTube export?"
> **Domain expert:** "No. If separate camera and screen sources exist, the **Source Lock** must prove those raw sources were used."

> **Dev:** "The layout is 1080x1920, so is the Short done?"
> **Domain expert:** "No. It is only a **Final Short** after the hook, karaoke caption, ending, style, silence, and decode gates pass."

## Flagged Ambiguities

- "Hook corpus" and "hook playbook" are the same concept; use **Hook Playbook**.
- "Studio Sound" means Eddy's local heavy speech enhancement gate unless a Descript project path is explicitly used.
