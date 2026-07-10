# Final promotion requires delivered-media retranscription

## Status

Accepted on 2026-07-10.

## Context

Source transcripts and edit plans describe intended cuts. They cannot prove what survived an
encoder, concat, audio service, motion composite, caption burn, or final mux. Eddy previously used
synthesized output timings, which allowed repeats, false starts, and long pauses to pass despite
being audible in delivered files.

## Decision

Eddy retranscribes every completed long and Short. The delivered word timings drive the final
cadence, repeat, reset-loop, false-start, and protected-pause gates. A transcription failure is a
blocking verification failure. Source-plan simulation remains useful for compilation receipts but
cannot promote media into `final/`.

Dual-source Shorts also prove source-mapped screen content from the delivered pixels and measure
their motion-only render at 10 fps before audio enhancement and promotion.

## Consequences

Finalization takes longer and can produce exact blockers after a media-valid render. That cost is
intentional: Eddy may quarantine a playable candidate, but it may not call an unverified candidate
complete.
