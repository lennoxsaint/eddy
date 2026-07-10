# Eddy decision log

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
