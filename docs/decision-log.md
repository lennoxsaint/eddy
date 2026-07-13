# Eddy decision log

## 2026-07-11 - Owner feedback becomes proof, regression, then guarded shipping

- The first owner-approved golden run is evaluated against `creator_good_v1`: editorial truth,
  pacing, layout, Studio Sound survival, contextual HyperFrames motion, screen proof, Shorts honesty,
  caption timing, and sentence-ending punctuation.
- Caption-only repairs reuse the approved final audio stream byte-for-byte. They do not start another
  Descript job, alter the three long videos, or promote until delivered-media gates pass again.
- Owner feedback is typed as run-specific, deterministic defect, quality preference, or doctrine.
  A future-facing lesson needs a regression before it may enter the canonical skill or runtime.
- Canonical changes ship through one guarded command that regenerates projections, runs all release
  gates, stages an explicit allowlist, pushes `eddy-v3/main`, waits for CI, and refreshes the owner
  plugin. Unconditional feedback auto-push remains forbidden.
- The owner `@eddy` plugin follows the canonical local V3 projection. Public installs remain pinned
  to immutable stable tags once the five-run trust gate permits a release.

This records the first run Lennox approved across all three longs and all three Shorts after the
only requested correction: restoring terminal punctuation in burned Short captions.

## 2026-07-11 - Captions and motion must follow the delivered environment

- Short caption timing is projected through the exact splice segment receipt. Eddy no longer
  invents a uniform 0.1-second duration for every word.
- Caption promotion compares the planned burned-caption timeline with a fresh transcript of the
  delivered Short. Word-match coverage, total duration, onset error, and cue hold time must pass.
- HyperFrames beats render as compact skeuomorphic desktop panels, not full-width opaque bands or
  giant centered text. The real base frame selects light/dark treatment and the quietest valid
  placement.
- Long-form placement reserves the camera PiP. Portrait placement reserves the face, caption band,
  and footer while leaving most of the raw screen proof visible.
- Placement metadata is not enough: Eddy samples the rendered overlay pixels for every beat and
  blocks promotion when coverage is excessive, the graphic escapes its assigned panel, or any pixel
  enters a reserved region.

This repairs the run where Short captions compressed 16-23 seconds of speech into 5-9 seconds and
where otherwise green motion covered the browser UI, source proof, and caption-safe regions.

## 2026-07-10 - Exact green Studio Sound renders are reusable proof

- Eddy caches a real Studio Sound output by the SHA-256 of the exact pre-audio MP4, never by title,
  timestamp range, or source filename.
- A cache hit requires an unchanged input hash, an unchanged cached-output hash, private Descript
  project/composition provenance, and a green effect-survival receipt. Any missing or altered proof
  becomes a cache miss and returns to the normal provider path.
- Cache hits copy the proven output, re-transcribe and re-run delivered-media QA, and receipt-log the
  original provider proof plus the current artifact mapping. Fake/local audio never enters the cache.

## 2026-07-10 - Provider retries are separate from effect retries

- A stopped Descript job, timeout, or transient API error gets up to three operational attempts with
  a short increasing backoff. These attempts do not consume the two-render budget reserved for an
  export where Studio Sound was reported applied but the waveform stayed unchanged.
- Failed jobs receipt-log Descript's sanitized status and error message before retrying. Auth,
  provenance, and hash faults still fail immediately.
- Persistent provider failure remains an exact blocker; Eddy never substitutes local EQ and calls
  it Studio Sound.

## 2026-07-10 - Short-only retakes need explicit splice inputs

- `shorts[].drop` is a backward-compatible source-time removal list for a retake that survives only
  inside a Short candidate.
- Eddy validates each removal against the Short source spans and protected content, subtracts it
  from screen-proof accounting, and merges it with shared-body drops for the actual camera splice.
- The merged inputs are receipt-logged. Delivered-media retranscription remains the promotion
  authority; this control repairs the edit rather than weakening the retake gate.

## 2026-07-10 - Descript operational failures retry before editorial repair

- A timeout, failed provider job, transient API status, missing import/publish result, or no-change
  agent result gets one fresh private Descript attempt inside the audio boundary.
- Authentication, authorization, connector provenance, and hash failures do not retry.
- Provider retries, effect retries, and terminal errors are preserved in artifact-scoped receipts;
  provider timeouts are no longer mislabeled as `descript_effect_not_rendered`.

This prevents a transient Descript job from consuming an entire editorial repair attempt after the
video edit, motion, and earlier audio outputs are already green.

## 2026-07-10 - Delivered callbacks inherit exact source-ledger resolutions

- Delivered-media retranscription remains the final editorial source of truth.
- A delivered repeat is treated as resolved only when two distinct delivered variants match two
  distinct variants from one source-ledger candidate explicitly reviewed as `intentional_repeat`.
- New repeats, unmatched variants, reset loops, and false starts remain blocking.

This repairs the free-model long where a reviewed opening promise and closing CTA callback was
incorrectly reclassified as an unresolved retake after delivery.

## 2026-07-10 - Portrait motion owns a portrait type scale

- HyperFrames stat beats use `160px` type inside a 1080px portrait Short while long-form landscape
  beats retain the approved `300px` scale.
- Stat and subtitle nodes are real stagger targets, so HyperFrames validation receipts stay complete
  instead of overflowing its warning-output cap with missing-target noise.
- Motion inspection remains blocking. Eddy fixes overflow at the composition source rather than
  bypassing `text_box_overflow` or falling back to a static captioned card.

This repairs the real demo Short where `ANY MODEL` overflowed the portrait frame and prevented the
motion overlay from rendering.

## 2026-07-10 - Missing Descript effects retry inside the audio boundary

- A provider response that says Studio Sound was enabled does not override an unchanged exported
  waveform.
- When the Effect-Survival Gate finds `descript_effect_not_rendered`, Eddy automatically starts one
  fresh private Descript render and repeats parity and waveform proof before returning a blocker.
- API errors, invalid exports, and timing drift still fail immediately. A second unchanged export
  still blocks, and no local-EQ fallback may populate `final/`.

This keeps the proof gate honest while removing a needless host-repair round trip for a transient
Descript export that acknowledged the effect but did not render it.

## 2026-07-10 - Delivered cadence gets bounded no-credit repair

- After Studio Sound, Eddy retranscribes the delivered long and repairs word-gap outliers by removing
  time from the already enhanced video. It never creates or replaces speech.
- Eddy allows up to three improving passes and stops on a repeated failure signature. Every pass
  records before/after violations, hashes, and its exact segment receipt.
- The repair retains Descript provenance, writes before/after hashes and a segment receipt, and does
  not start another paid provider job.
- The audio-silence ceiling remains `0.28s`; word alignment gets 20 ms of tolerance for Whisper
  boundary jitter. Individual sub-0.8s word gaps are diagnostic when delivered audio silence and p95
  are green; sustained slow p95 cadence or an extreme word gap still blocks and triggers repair.
- Repeat evidence needs a content-bearing shared n-gram. Generic scaffolding such as “and this is
  the” cannot group unrelated claims into a retake, and a single ellipsis cannot turn every nearby
  “So...” sentence into a reset loop.

This repairs the real candidate where a no-credit cadence pass moved p95 to `0.141s` and left only a
`0.281s` alignment reading, while the prior detector incorrectly grouped normal explanatory prose.

## 2026-07-10 - Measured silence owns pacing cuts

- Transcript word protection applies only to transcript-inferred gaps. Measured audio silence cannot
  be hidden by an implausibly long Whisper word timestamp.
- Kept spans start 60 ms before their first word and end 40 ms after their last word, so separate
  source edges cannot accumulate into a slow delivered join.
- The creator-footage silence floor is `-27 dB`; the delivered `-30 dB` verifier still enforces the
  `0.28s` ceiling. The calibration edit measured a `0.269s` worst pause before Studio Sound.

This repairs the false pacing proof where raw room tone plus malformed word durations survived the
cut and Studio Sound later exposed those retained intervals as obvious dead air.

## 2026-07-10 - Studio Sound promotion uses provider and signal truth

- Descript success, `project_changed`, private provenance, duration parity, and a material waveform
  change are the blocking Studio Sound proof chain.
- Unchanged audio, gain-only audio, invalid exports, provider failures, and timing drift still block.
- Echo and voice-texture metrics stay in receipts for listening review but cannot independently veto
  promotion because they are not calibrated classifiers for Descript's proprietary effect.

This is the smallest repair for the real 100% Studio Sound audition that Descript confirmed and that
changed the waveform materially, but which Eddy falsely rejected using an absolute echo heuristic.

## 2026-07-10 - Editorial truth belongs to delivered media

- Preflight creates an Editorial Review Ledger from the complete transcript and measured audio.
- The host reviews every transcript chunk and resolves every candidate; Eddy compiles those
  resolutions into explicit source-time drops.
- Protection may retain meaning but never conceal more than 0.8 seconds of silence.
- Final promotion depends on retranscribing and rechecking every delivered long and Short.
- Dual-source Shorts require at least 25% verified raw-screen proof and two measurably animated
  HyperFrames beats. Generated cards may support proof but cannot replace the source recording.
- A red attempt is quarantined with a repair packet. Three red attempts block the job.

This decision repairs the false-green path where accepted fields were ignored, source-plan timing
stood in for delivered-media truth, and static Shorts panels were described as proof or motion.

## 2026-07-10 - Top-level raw media wins over nested run artifacts

When a selected source folder contains top-level media, Eddy treats those files as the complete
source set. It does not recursively ingest nested prior `runs/`, `eddy-runs/`, `work/`, `final/`,
cache, output, or quarantine media. This prevents recursive output pollution and ambiguous screen
selection. Transcript reuse is allowed only under the immutable camera SHA-256 and is receipted.

## 2026-07-10 - Render once at each ownership boundary

- Splices seek to their first kept source frame and decode only the bounded edit window.
- Audio uses one `asegment` pass; an N-way `atrim` graph is forbidden for large edits.
- Video intervals are end-exclusive and retain source-relative duration, preventing per-cut frame
  rounding from accumulating A/V drift.
- Screen intermediates normalize to 1080p before composition.
- The shared screen/PiP body is styled once. Hook layouts are joined by stream copy so all three
  longs inherit the identical body without redundant recompression.

These mechanics preserve source-time receipts while materially reducing preview latency and
generation loss.

## 2026-07-10 - Descript is full-intensity, receipted, and fail-fast

Eddy requests Studio Sound on every clip at the configured intensity, including an explicit 100%
request. It records Underlord's result, whether the project changed, resolved model, and AI credit
use without retaining private project identifiers in support bundles. The first failed
Effect-Survival Gate ends the attempt before additional paid jobs; later outputs cannot rescue a
required red audio gate.

## 2026-07-13 - Studio Sound never requires AI Speaker consent

- Studio Sound is requested as a file-level audio cleanup effect on imported recorded media.
- Eddy explicitly forbids AI Speaker creation, AI Speech, Regenerate, text-to-speech, overdubbing,
  and voice generation in the Studio Sound prompt.
- A `no_verified_consent` response is evidence that Descript's agent misrouted the request through
  AI Speaker policy, not evidence that Studio Sound itself requires consent.
- Eddy sends one corrective audio-effect-only prompt. If the agent repeats the misroute, Eddy emits
  `descript_studio_sound_agent_misrouted` and routes to the authenticated host/UI effect path; it
  never asks the owner to record voice consent for Studio Sound.
- Promotion still requires private provider provenance, duration parity, and a materially changed
  exported waveform.

This follows Descript's product boundary: consent belongs to generated AI Speakers, while Studio
Sound cleans recorded audio. The correction was proved on the same July 13 private project that had
first returned `no_verified_consent`; the corrected export passed effect survival at correlation
`0.83978672` with `0.007271s` duration delta.

## 2026-07-13 - Incidental people are redacted before owner approval

- A host plan may declare deterministic privacy masks scoped to named Long hooks.
- Masks use delivered-relative time and validated 1920x1080 rectangles, and are burned into the
  motion-complete render before Studio Sound.
- The source snapshot remains immutable. A configured mask that does not render blocks the attempt.
- Redaction happens before private staging so the owner full-watch receipt binds the exact file that
  can later become the Canonical Master.

This prevents an approval receipt from becoming stale merely because an incidental comment, handle,
or other private evidence was discovered after staging.

## 2026-07-13 - Green candidates reopen only through typed owner repair

- `owner-feedback-v1` with `verdict: changes_requested` is the sole route from `completed` back to
  `awaiting_host_repair`.
- Eddy moves the completed candidate into its numbered quarantine attempt before accepting another
  plan, keeping the source lock and evidence chain intact.
- The same three-attempt ceiling applies. A rejection after attempt 3 moves the job to `blocked`.

This preserves the difference between a proof-gated edit and an owner-accepted edit without allowing
manual state edits or off-pipeline media replacement.

The owner plugin may be launched by a desktop host that does not inherit shell startup variables.
When `DESCRIPT_API_KEY` is absent from the process, Eddy reads only a literal exported value from the
owner's `~/.zshenv`; it never executes the file, expands shell expressions, or logs the token.

Delivered intentional callbacks may be a reviewed subset of a larger source repeat candidate after
false starts and discarded takes are removed. Eddy requires every delivered variant to match a
distinct reviewed source variant; extra unreviewed delivered variants still block.
