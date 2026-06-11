# Shorts Feedback Ledger

Purpose: capture reusable Yazzy/Lennox feedback so future Shorts edits improve instead of repeating the same approval loop.

## Schema

Each entry should use this compact shape:

- `date`: YYYY-MM-DD
- `project/video`: source project or video name
- `short/sample`: affected Short or sample
- `feedback`: what Yazzy/Lennox said
- `diagnosis`: what went wrong or what preference was clarified
- `new rule`: reusable rule to apply next time
- `applies to`: layout, captions, pacing, retakes, crop, screen, workflow, or all Shorts
- `status`: proposed, accepted, superseded, or rejected

Only promote feedback into a reusable rule when it changes future behavior. One-off sample notes can remain tied to that sample. When rules conflict, mark the older rule `superseded` and explain the newer rule.

## Accepted Rules

### 2026-05-31 — Codex 2026-05-29-landed-2300-month-client — Clients Hunt You v3

- `date`: 2026-05-31
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: Clients Hunt You v3
- `feedback`: The webcam was too large and did not look right.
- `diagnosis`: The face crop dominated the vertical frame instead of presenting Lennox as a balanced square crop.
- `new rule`: Use a balanced square face-cam crop showing head, headphones, shoulders, and upper chest; do not oversize the webcam.
- `applies to`: layout, crop
- `status`: accepted

- `date`: 2026-05-31
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: Clients Hunt You v3
- `feedback`: The sample had no captions.
- `diagnosis`: A Short render without visible captions fails the expected Descript-inspired style.
- `new rule`: Captions are mandatory; use karaoke-style word states with current word highlighted, previous words bright, and future words dim.
- `applies to`: captions
- `status`: accepted

- `date`: 2026-05-31
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: Clients Hunt You v3
- `feedback`: The cropped slide should match the width of the actual video frame instead of being expanded to fill/crop aggressively.
- `diagnosis`: Screen crops that enlarge too much lose context and reduce readability.
- `new rule`: Bottom screen panel should fit the full source width with padding unless a specific proof moment needs a careful zoom.
- `applies to`: screen, layout
- `status`: accepted

- `date`: 2026-05-31
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: Clients Hunt You v3
- `feedback`: There were still lots of word gaps and retakes.
- `diagnosis`: Broad timestamp ranges preserved dead air, false starts, and weak repeated takes.
- `new rule`: Audit transcript word timings before render, then split Shorts into phrase-level keep ranges that remove obvious gaps and retakes while preserving natural micro-pauses.
- `applies to`: pacing, retakes
- `status`: accepted

- `date`: 2026-05-31
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: all Shorts
- `feedback`: `book4short` is meant to be `Hook for Short`.
- `diagnosis`: Transcription variants can hide Short markers.
- `new rule`: Treat `book4short`, `book for short`, and close variants as `Hook for Short` markers.
- `applies to`: transcript, workflow
- `status`: accepted

- `date`: 2026-05-31
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: all Shorts
- `feedback`: Generate one sample clip first, then iterate until approved before recreating all Shorts.
- `diagnosis`: Batch rendering before the style is approved wastes review time and can multiply a bad layout.
- `new rule`: Use a sample-first approval loop and preserve previous exports as rollback.
- `applies to`: workflow
- `status`: accepted

### 2026-06-01 — Codex 2026-05-29-landed-2300-month-client — Batch QA Repair

- `date`: 2026-06-01
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: Do Free Work Strategically
- `feedback`: Retakes were still left in, and review found multiple errors in the first two minutes of the Shorts folder.
- `diagnosis`: Visual contact-sheet QA and metadata checks were not enough; the rendered Short still contained repeated takes and dead-air gaps.
- `new rule`: Before asking for user review, run transcript-level kept-text QA on every generated Short and fail the batch if any obvious retake, repeated hook, false start, marker leakage, clipped phrase, or weak abandoned tail remains.
- `applies to`: pacing, retakes, workflow, all Shorts
- `status`: accepted

- `date`: 2026-06-01
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: Bounded First Phase
- `feedback`: The ending cut off around the line ending in "in writing" and left silence.
- `diagnosis`: A phrase boundary looked acceptable in the contact sheet but failed when watched as a full rendered video.
- `new rule`: Watch or decode-check final rendered Shorts after phrase edits; use silence detection on final MP4s and map any internal silence over 1.2 seconds back to raw transcript times before review.
- `applies to`: pacing, workflow, all Shorts
- `status`: accepted

- `date`: 2026-06-01
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: all Shorts
- `feedback`: QA needs to be much more improved; the user should not have to keep finding the errors.
- `diagnosis`: Batch-level editorial QA was too shallow and relied on user review as the error detector.
- `new rule`: When one Short fails QA, re-audit the whole batch with independent transcript review, rendered media checks, and targeted fixes before returning any more files for review.
- `applies to`: workflow, all Shorts
- `status`: accepted

- `date`: 2026-06-01
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: all Shorts
- `feedback`: Use subagents if it helps.
- `diagnosis`: Parallel read-only review caught retained retakes and clipped phrases faster than a single pass.
- `new rule`: For batches with many Shorts, or after the user finds repeated editorial misses, use subagents for read-only transcript QA while the main agent owns final edits, renders, and verification.
- `applies to`: workflow, all Shorts
- `status`: accepted

- `date`: 2026-06-01
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: all Shorts
- `feedback`: The batch was closer but still only around 80%; last words were sometimes cut off, `Never Sign The First Contract` was silent at the beginning, and random silent moments remained.
- `diagnosis`: Prior QA allowed rendered files through when the transcript looked clean but the final MP4 still had start silence, clipped-tail risk, or audible dead-air pockets.
- `new rule`: Before asking for review or upload, run final-render QA on every Short: confirm 1080x1920 video and audio streams, no start silence over 0.16s, no end silence over 0.45s, no internal silence over 0.60s, and a secondary borderline scan around 0.50s to manually inspect or fix the clearest pauses. Confirm final words with a tail handle or rendered silence check.
- `applies to`: pacing, workflow, all Shorts
- `status`: accepted

- `date`: 2026-06-01
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: Let Them Name The Price / Do Not Sign First Contract / all Shorts
- `feedback`: `Do Not Sign The First Contract` should not be used; `Let Them Name The Price` ended in a weird space; stop ending things in the middle of sentences.
- `diagnosis`: Silence detection alone can pass a clip that still ends on a dangling thought, setup phrase, connector, or rejected editorial premise.
- `new rule`: Before upload-readiness, run semantic transcript-ending QA on every Short in addition to media silence QA. A Short must end on a complete spoken thought, not a connector, abandoned setup, or mid-sentence fragment. If the user rejects a Short, exclude it from the upload-ready folder and manifest instead of trying to force it through.
- `applies to`: pacing, workflow, all Shorts
- `status`: accepted

- `date`: 2026-06-01
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: all Shorts
- `feedback`: The final reels still ended mid-sentence and were not upload ready.
- `diagnosis`: Earlier QA treated punctuation, file existence, and visual contact sheets as enough. That missed cases where the selected endpoint was still an unfinished beat, pulled in the next word, or left real dead air.
- `new rule`: Upload-ready Shorts require a sentence-final ledger before review: record the exact final selected line and the raw transcript words immediately after the cut for every Short, then fail any ending that is not a complete sentence and complete thought. Also generate a tail-ending QA reel from the final rendered MP4s and run true dead-air detection on the final files before calling the folder ready.
- `applies to`: pacing, endings, workflow, all Shorts
- `status`: accepted

- `date`: 2026-06-01
- `project/video`: Codex 2026-05-29-landed-2300-month-client
- `short/sample`: all Shorts
- `feedback`: Words were still being cut off halfway through across the reels.
- `diagnosis`: Transcript-clean and sentence-final QA can still pass when FFmpeg cuts are too close to the actual waveform. Whisper word timings are approximate, and over-tight microcuts can shave syllables even when the written transcript looks correct.
- `new rule`: Upload-ready Shorts need audio-boundary QA, not just transcript QA. For every phrase cut, keep practical audio handles around the first and last spoken words, hard-fail any boundary under 100ms, manually review boundaries under 120ms, and prefer a slightly longer natural pause over a clipped syllable. After render, run final MP4 silence detection and remove only the center of internal low-audio spans while leaving handles on both sides.
- `applies to`: pacing, clipped words, workflow, all Shorts
- `status`: accepted

### 2026-06-06 — Codex Agent Productivity System — Long-Form/Short Marker Flow Feedback

- `date`: 2026-06-06
- `project/video`: Codex 2026-05-30-codex-agent-productivity-system
- `short/sample`: all Hook for Short markers
- `feedback`: If the first line after a `Hook for Short` marker does not flow with the before/after context in the long-form script, it can be deleted from the long edit to preserve seamlessness.
- `diagnosis`: A sentence can be a useful standalone Short hook while still feeling abrupt or disconnected inside the long-form argument after marker removal.
- `new rule`: For long-form edits, remove the marker, then audit the first post-marker sentence in context. If it only functions as a Short opener, repeats a setup, or breaks the long-form flow, remove that sentence from the long edit while preserving it as a possible Short candidate.
- `applies to`: transcript, workflow, long-form cleanup, all Shorts
- `status`: accepted

### 2026-06-06 — Codex Agent Productivity System — Visual Approval Is Not Editorial Approval

- `date`: 2026-06-06
- `project/video`: Codex 2026-05-30-codex-agent-productivity-system
- `short/sample`: approved visual layout sample
- `feedback`: The visuals were approved, but the sample itself was still a weak Short because it did not clearly deliver value or make someone want to watch the full video.
- `diagnosis`: The workflow treated sample approval as enough momentum to batch-render, even though sample approval may only validate crop, caption style, and layout.
- `new rule`: Separate visual/render approval from editorial/moment approval. After a visual sample is approved, re-score the actual Shorts candidates for first-3-second grip, standalone value, and full-video pull before batch rendering. Drop or replace any candidate that looks good but has weak viewer payoff.
- `applies to`: hookability, workflow, all Shorts
- `status`: accepted

### 2026-06-06 — Codex Agent Productivity System — Approved Layout Requires Separate Sources

- `date`: 2026-06-06
- `project/video`: Codex 2026-05-30-codex-agent-productivity-system
- `short/sample`: approved visual reference screenshot
- `feedback`: The batch did not look like the approved example. The correct look has a large clean camera panel, big karaoke captions directly underneath, and a full-width screen/proof panel below. The flattened longform export crop looked like tiny panels and was not acceptable.
- `diagnosis`: The renderer reused the approved layout concept but changed the source class from separate camera/screen to a flattened longform export. That source drift made it impossible to match the reference.
- `new rule`: Sample approval is source-specific. If the approved sample was built from separate camera and screen sources, future batches must use equivalent separate sources or a Descript timeline export with included media. If only a flattened export is available, fail closed and report the source-media blocker instead of rendering a substitute batch.
- `applies to`: visual layout, source media, QA, all Shorts
- `status`: accepted

### 2026-06-09 — Session Audit — Approved Shorts Style Must Not Drift

- `date`: 2026-06-09
- `project/video`: reusable video-editing SOP
- `short/sample`: all Shorts with an approved sample or style lock
- `feedback`: Yazzy had to correct the agent for changing the Shorts style after being specific about it, including the talking-head shape and caption style.
- `diagnosis`: The workflow treated later long-form motion direction as permission to restyle Shorts. That created style drift from the approved source-layer look.
- `new rule`: Once a Short sample or style lock is approved, fail closed if a renderer changes source class, caption colors, karaoke behavior, headshot geometry, rounded-square mask, proof-panel placement, or border treatment without explicit approval. Long-form red/white/black motion direction does not override blue karaoke Shorts captions.
- `applies to`: layout, captions, crop, source media, workflow, all Shorts
- `status`: accepted

### 2026-06-09 — Session Audit — Source Identity Before Shorts Render

- `date`: 2026-06-09
- `project/video`: reusable video-editing SOP
- `short/sample`: all Descript-backed Shorts
- `feedback`: Yazzy had to steer the edit back to the correct video/composition after the wrong project source was used earlier in the workflow.
- `diagnosis`: Same-named Descript exports and old local source folders can look plausible while belonging to the wrong composition.
- `new rule`: Before any Descript-backed Short render, write or read a source-lock receipt that proves the target project/video name, composition or timeline id when available, source folder, expected duration range, and forbidden stale folders/ids. Do not render from old same-named media or flattened longform exports when the approved layout requires source layers.
- `applies to`: source media, workflow, QA, all Shorts
- `status`: accepted
