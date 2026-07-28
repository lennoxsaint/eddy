# ADR 0008: Durable VSL corrections and independent proof

Date: 2026-07-28

## Decision

Eddy adds `lennox-professional-youtube-v2`, `eddy-host-packet-v3.2`,
`edit-plan-v3.5`, and `eddy-contract-bundle-v2`. The owner profile stores reusable taste defaults;
the Project Fact Brief stores names, offers, links, brand facts, identities, and one-off choices;
core validators own source safety, sample-exact integrity, cache invalidation, objective media
measurements, and proof-state transitions.

V3.5 renders remain outside `final/` until an independent no-edit verifier submits three complete
review passes, a mechanically recomputed 100-point score, every professional gate with hash-bound
evidence, complete full-watch/full-listen coverage, and zero objective open items. Passing moves the
run only to `proof_gated_candidate_awaiting_owner_taste`. An explicit `owner-verdict-v2` controls
approval or reopens the same run.

Ordinary Eddy is still a host-agent-driven single-editor workflow. It continues repair in the same
active task without asking the owner to say “continue,” but this decision adds no daemon,
background controller, publishing code, or bake-off launcher.

The standalone video-edit-bakeoff skill remains model-neutral and prepare-only. Its v2 manifest
freezes Eddy, profile, brief, design, verifier, correction, source, and audio hashes equally for
every contestant while keeping model identities and blind mappings outside Eddy.

## Consequences

- Legacy profiles and plans remain readable but cannot claim the v2 proof state.
- Filename reuse cannot preserve stale derived evidence because cache keys bind content bytes.
- Waveform evidence may override transcript timing when the two conflict.
- Long designed captions default off; Shorts use progressive, speaker-attributed captions.
- One-off facts cannot become reusable doctrine without passing anti-overfitting validation.
- Gate failure quarantines the attempt and requires a changed strategy; gates are never weakened.
