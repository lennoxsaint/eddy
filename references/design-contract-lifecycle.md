# HyperFrames design-contract lifecycle

Eddy pins HyperFrames v0.7.3 at commit
`997823b6b523eb4d43e0f03c140f5897f13ce780`. The four approved teaching files and
their hashes live in `hyperframes-doctrine-v0.7.3.json`; exact copies are bundled under
`hyperframes-v0.7.3/`.

## Precedence

1. Current run instruction.
2. Supplied project brand.
3. Selected owner editing/taste profile.
4. HyperFrames house style.

`design.md` holds project brand truth. Root `frame.md` owns landscape Long geometry.
`shorts/frame.md` owns portrait Short geometry. YAML frontmatter is normative; prose is contextual.

## Creation

At `eddy_edit_start`, Eddy:

1. Detects a supplied `design.md`, `DESIGN.md`, or narrow brand-token JSON without changing it.
2. Creates run-local `design.md`, `frame.md`, and `shorts/frame.md`.
3. Snapshots the selected profile, 100-point rubric, correction evals, and four HyperFrames
   references into `contracts/`.
4. Writes `contracts/contract-bundle.json` with provenance, revisions, and SHA-256 hashes.
5. Returns matching refs and hashes through `eddy-host-packet-v3.1`.

The host enriches the run-local contracts before submitting v3.4 when the detected evidence is not
enough. Another checkout is never hotlinked at render time.

## Static-first composition

Every hero frame is built and inspected as a static composition before animation. Static review
checks typography at video scale, safe zones, caption bands, proof/UI collision, hierarchy,
contrast, mobile legibility, and evidence fidelity. Animation begins only after the frame works
without movement.

Animation must reveal, connect, compare, focus, or change state. Layout changes, zooms, and
transitions require a written semantic cause. Automated drift, filler punch-ins, tiny proof,
decorative motion, and paragraph-heavy cards fail adherence.

## Repair and revision

Use `eddy_revise_design_contracts` or `eddy revise-design` only for a systemic project design
defect. The operation:

- archives the prior affected contracts;
- increments only affected revisions;
- records the reason and from/to hashes;
- invalidates dependent renders;
- requires lint, validate, strict inspect, snapshots, design adherence, contrast, and animation-map
  review again.

A one-off project correction remains local. At owner approval, Eddy may propose the reusable part
for promotion into the owner profile. Promotion is a separate reviewed change with a regression
eval; it is never automatic.
