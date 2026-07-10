# Descript effects require survival proof

Eddy treats Descript job success and duration parity as necessary but insufficient. Final audio must
also pass an Effect-Survival Gate; otherwise the run blocks with `descript_effect_not_rendered`.
The gate requires a successful provider edit, a changed project, private export provenance, duration
parity, and a waveform change larger than an unchanged codec round trip. This rejects unchanged beta
exports and forbids silently substituting local EQ, raw audio, or another cloud enhancer under the
Studio Sound name.

Echo and voice-texture measurements remain in receipts for owner review, but they are not blocking
classifiers. The former absolute echo threshold falsely rejected a Descript-confirmed 100% Studio
Sound export even though its duration matched and its normalized source correlation fell to 0.8513.
That heuristic was not calibrated against Descript output and could not identify whether Descript's
effect was applied, so it must not overrule the provider and signal-survival evidence.
