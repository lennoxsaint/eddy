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

**Creator-Good Edit**:
The default YouTube edit state: retakes are transcript-hard removed, one clean hook survives, gaps feel tight-natural, strong local audio cleanup is proven, first-60 motion is composited, and Shorts are green or exactly blocked.
_Avoid_: Rendered successfully, media-valid, "good enough"

**Edit Path**:
The user-visible route Eddy uses for editorial decisions while Eddy still owns source safety, rendering, QA, and receipts.
_Avoid_: Provider only, model choice

**Host-Agent Edit**:
An edit path where the current assistant session supplies structured editorial decisions from an Eddy packet, and Eddy compiles, renders, and gates the result.
_Avoid_: Codex-only mode, manual editor

**Retake-Clean Edit**:
An edit where failed hook attempts, false starts, repeated takes, and reset loops do not survive the final timeline.
_Avoid_: Media-valid edit, best visible take somewhere in the file

**Transcript-Hard Retake Removal**:
Retake deletion driven by grouped word/phrase evidence from the raw transcript. Non-selected variants are hard removed unless the host protects one with receipt evidence.
_Avoid_: Retake hints, model vibe, optional cleanup

**Opening Hook Cluster**:
Multiple opening attempts before the first real body section. Eddy keeps one variant, defaulting to the best clean hook with latest complete clean hook as fallback unless the host explicitly protects an earlier stronger hook.
_Avoid_: Keeping every intro attempt, model-decided first hook by accident

**Best Clean Hook**:
The single hook variant Eddy keeps from an opening cluster: strongest complete, intelligible, non-flubbed hook; latest clean complete hook wins when no host choice is provided.
_Avoid_: First attempt, most recent flub, all hooks

**Word-Onset Safety**:
Cut mechanics that preserve audible first syllables and natural lead-in handles, not only transcript word centers.
_Avoid_: Text-green but clipped speech, tiny boundary pads

**Gap Pacing Gate**:
A creator-facing pacing gate that collapses ordinary spoken-word gaps toward a tight-natural range around 0.35s-0.55s while preserving protected or intentional pauses.
_Avoid_: Draggy word gaps, ultra jump-cutting, dead-air-only QA

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

**Strong Studio Sound**:
A Studio Sound result whose selected profile used a heavy/wet cleanup path and passed click, echo, loudness, and strong-cleanup gates.
_Avoid_: `source_reference` selected, loudness-only normalization

**Local Studio Sound Audition**:
The local A/B matrix Eddy writes for hook and worst-click windows before selecting a heavy cleanup profile. If clicks, echo, loudness, or voice texture cannot be measured green, packaging blocks.
_Avoid_: Zero-signal detector pass, source-reference winner, cloud audio by accident

**HyperFrames Frame Contract**:
The project-local `frame.md` motion design system that governs overlays before animation.
_Avoid_: Ad hoc ffmpeg boxes, one-off overlay

**First-60 HyperFrames Motion Layer**:
The required default YouTube motion phase that copies pinned HyperFrames assets, writes frame/storyboard proof, renders a first-30-to-60-second overlay, probes it, and composites it without changing cleaned audio.
_Avoid_: Static long-form only, missing asset cache, unproven overlay

**Storyboard Proof**:
A static `storyboard.html` inspection surface that proves every planned motion frame before animation.
_Avoid_: Trusting the animated render first

## Relationships

- A **Hook Playbook** scores many candidate clips, but only quality-gated candidates become **Final Shorts**.
- A **Final Short** must have exactly one **Source Lock** and one **Style Lock** receipt.
- A **Proof-Gated Edit** may use one or more **Edit Path** attempts, but the edit is not complete until gates pass.
- A **Creator-Good Edit** is the default **Proof-Gated Edit** target for `Eddy, edit this`.
- A **Host-Agent Edit** is an **Edit Path**, not a replacement for Eddy's deterministic compiler or QA.
- A **Retake-Clean Edit** depends on **Transcript-Hard Retake Removal**, **Opening Hook Cluster** handling, and repeated-take simulation gates.
- **Word-Onset Safety** is required for every **Retake-Clean Edit**; a transcript-valid cut can still fail if audio starts are clipped.
- A **Gap Pacing Gate** can fail even when dead-air gates pass.
- A **Route Fallback** keeps one run history; it must not hide which **Edit Path** produced each decision.
- **Studio Sound** is an audio gate for both long-form videos and **Final Shorts** unless explicitly disabled for tests.
- **Strong Studio Sound** is the default passing Studio Sound state when heavy cleanup is required and is selected through **Local Studio Sound Audition**.
- A **HyperFrames Frame Contract** produces a **Storyboard Proof** before any motion graphic is composited.
- A **First-60 HyperFrames Motion Layer** is required for default YouTube edits unless explicitly disabled for tests/advanced runs.

## Example Dialogue

> **Dev:** "Can I render Shorts from the finished YouTube export?"
> **Domain expert:** "No. If separate camera and screen sources exist, the **Source Lock** must prove those raw sources were used."

> **Dev:** "The layout is 1080x1920, so is the Short done?"
> **Domain expert:** "No. It is only a **Final Short** after the hook, karaoke caption, ending, style, silence, and decode gates pass."

> **Dev:** "The model got stuck but the proxy is watchable. Is that a perfect edit?"
> **Domain expert:** "No. A **Proof-Gated Edit** is either gate-green or it returns exact blockers and route history."

> **Dev:** "The intro has three hook attempts, but the final file plays fine."
> **Domain expert:** "No. A **Retake-Clean Edit** keeps one **Opening Hook Cluster** variant and removes the failed attempts."

> **Dev:** "There are no 2-second dead-air spans, but the pauses still drag."
> **Domain expert:** "No. The **Gap Pacing Gate** is separate from dead-air detection; ordinary spoken-word gaps need to land in the tight-natural range."

> **Dev:** "The transcript starts on the right word, but the first syllable sounds shaved."
> **Domain expert:** "No. **Word-Onset Safety** is an audio-boundary gate, not a transcript-only gate."

> **Dev:** "The audio normalized and did not crash. Is Studio Sound done?"
> **Domain expert:** "No. **Local Studio Sound Audition** must select a heavy/wet cleanup result that passes mouth-click, echo, loudness, and texture gates."

> **Dev:** "Can the default YouTube edit skip motion graphics?"
> **Domain expert:** "No. A **Creator-Good Edit** includes the **First-60 HyperFrames Motion Layer** or returns an exact HyperFrames cache/render blocker."

## Flagged Ambiguities

- "Hook corpus" and "hook playbook" are the same concept; use **Hook Playbook**.
- "Studio Sound" means Eddy's local heavy speech enhancement gate unless a Descript project path is explicitly used.
- "`source_reference` is a do-no-harm audio comparison, not **Strong Studio Sound** when heavy cleanup is required."
- "Perfectly edited" means **Proof-Gated Edit**, not universal subjective perfection or a weak best-attempt proxy.
- "`Eddy, edit this`" means **Creator-Good Edit** by default, not merely media-valid long-form export.
