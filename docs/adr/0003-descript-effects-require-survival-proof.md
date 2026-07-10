# Descript effects require survival proof

Eddy treats Descript job success and duration parity as necessary but insufficient. Final audio must
also pass a calibrated Effect-Survival Gate; otherwise the run blocks with
`descript_effect_not_rendered`. This deliberately rejects unchanged beta exports and forbids silently
substituting local EQ, raw audio, or another cloud enhancer under the Studio Sound name.
