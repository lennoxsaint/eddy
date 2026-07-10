# Eddy V3 replacement plan

Status: approved implementation contract

## Repository and distribution

- Eddy V3 is the canonical product and repository.
- The current public `lennoxsaint/eddy` repository becomes the archived
  `lennoxsaint/eddy-legacy` repository.
- After the release gates pass, the V3 repository takes the public
  `lennoxsaint/eddy` name and ships as `v3.0.0`.
- Owner installs follow `main`. External and plugin installs resolve stable tags.
- Codex and Claude surfaces are generated projections of the same canonical skill.

## Product contract

- Produce three complete long-form videos: one primary version and two alternate
  hooks sharing one body.
- Produce three to five quality-gated Shorts.
- Produce video artifacts and proof only. Publishing, titles, thumbnails, launch
  packaging, and public distribution are out of scope.
- HyperFrames owns the motion layer. Selected proven V2 safety mechanics may be
  ported, but the V2 and V3 engines must not be merged.

## Audio and proof

- Descript Studio Sound is required for final audio.
- A direct Descript API path and an optional host connector may supply the
  processed audio, but final promotion requires proof that the effect survived.
- A red attempt is quarantined and can never be promoted to final.
- Every proof claim must distinguish candidate, quarantined, final, and
  owner-approved states.

## Runtime and trust

- The runtime is skill-first with a thin asynchronous MCP control plane.
- The no-review claim remains locked until five distinct green dogfood runs have
  explicit owner approval.
- Repository rename, public replacement, archive, and `v3.0.0` release happen only
  after the quality, sync, safety, and dogfood gates are green.
