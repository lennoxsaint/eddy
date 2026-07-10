# Eddy decision log

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
