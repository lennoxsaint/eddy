# Known limits

Honest scope boundaries as of v1.0. These are documented gaps, not bugs — don't file them as
defects; if one blocks you, that's a feature request.

## Editing model
- **Single-speaker assumption.** Eddy edits as if one speaker is talking. It *detects* likely
  multi-speaker/interview footage and warns (heuristic, low/medium confidence), but it does **not**
  diarize, attribute lines, or cut per speaker. Interview/podcast cuts need a human review pass.
- **No vision judging.** Thumbnail A/B pairing is by file, not visual quality — there is no vision
  model ranking frames. Title A/B uses a deterministic text rubric.
- **Speed ramps in the editor EDL.** The CMX3600 export records the correct *record* duration for
  retimed beats plus an `M2` motion-memory line; NLEs that ignore M2 still get aligned cut points
  but won't reproduce the ramp itself. A basic EDL can't fully represent a ramp.

## Captions
- **No RTL shaping / CJK glyphs in burned captions.** Burned word-captions are drawn left-to-right
  with no bidi reordering or Arabic joining, and the bundled Latin fonts lack CJK glyphs. Eddy
  detects RTL/CJK and warns; use the sidecar `.srt`/`.vtt` (shaped by the player) for those scripts.

## Inputs / formats
- **Audio-first is transcribe-only.** `.mp3`/`.wav` are accepted for `eddy transcribe`, but
  `eddy run` needs a video stream — there is no audio-only (audiogram) render path yet.
- **VFR/HDR** sources are normalized for rendering; exotic color pipelines may need a pre-conform.

## Reproducibility
- **Cloud brain isn't reproducible.** A Claude/OpenAI editorial brain is recorded-and-warned, not
  frozen. Bit-exact reproducibility requires the local qwen model at `temperature=0` + a fixed
  `seed` on the same model **digest** (see `docs/REPRODUCIBILITY.md`).

## Offline / egress guard
- **The egress guard is in-process only.** Under `--local-only`/`EDDY_OFFLINE` it blocks outbound
  non-loopback connections from Eddy's own process (covers httpx + the Anthropic/OpenAI SDKs +
  urllib; blocking `connect`, `connect_ex`, `create_connection`). It does **not** sandbox child
  processes. CLI-subprocess editorial brains (`claude_cli`/`codex_cli`) run in a child with their
  own socket stack — so offline mode **refuses to select them** (hard error) rather than trusting a
  guard that can't reach them. It also does not cover raw UDP/QUIC (no Eddy code path uses them).

## Platform / distribution
- **Cross-platform is authored + CI-gated, not yet hardware-dogfooded** on Windows/Linux from the
  maintainer's machine. The 3-OS CI matrix proves it once the private remote exists (human-gate).
- **No signed/notarized installers yet.** Requires Apple Developer ID + Windows Authenticode certs
  (human-gate). Install via `pipx` from source or the offline wheelhouse meanwhile.
- **No auto-update.** Update manually (`pipx upgrade` / `git pull` + `pipx reinstall`).

## Coverage
- The unit-coverage floor reflects pure logic; the render/whisper/ffmpeg paths are covered by the
  opt-in synthetic e2e + golden suite rather than counted unit coverage.

## Open tracking item
- **EDD-84** — tracked in `docs/decision-log.md`; see that entry for current status/scope.
