# Project Fact Brief

`project-fact-brief.json` carries facts that must not leak into Eddy doctrine. It uses
`eddy-project-fact-brief-v1` and is hash-bound into `eddy-contract-bundle-v2`.

The brief may supply:

- people, spellings, and speaker identities;
- brand tokens and owned assets;
- verified URLs, claims, offer, price, currency, and CTA;
- factual UI surfaces and their source bindings;
- an optional runtime target and Long-caption override;
- Studio Sound assets or an authorized treatment route;
- supplied music, licence evidence, and protected deliberate repetitions or pauses.

Every fact with a value needs a source reference. Essential facts use `required: true`; if their
value or evidence is missing, Eddy stops with `project_fact_required_missing:<id>`. Nonessential
facts are omitted. Eddy never guesses, invents a placeholder, or promotes these values into an
owner profile or generic doctrine.

Real captures are preferred for factual product and site claims. A reconstruction is allowed only
when all factual elements bind to verified brief evidence. Its internal receipt must keep
`evidence_kind: reconstructed`; it may omit an on-screen illustration label only when the rendered
facts remain completely faithful.
