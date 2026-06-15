# Reproducibility

"Same footage in → same edit out" is a GA promise, but it has two tiers because part of the pipeline
is deterministic code and part is a language model.

## Tier 1 — the deterministic core (byte-reproducible)

Everything downstream of the editorial decisions is pure, deterministic code:

- **EDL compilation** (`edit/compiler.py`) — given the same `edit-decisions.json`, `compile_edl`
  produces a byte-identical `edl.json`.
- **Simulation / QA math** (`edit/simulate.py`, `qa/deterministic.py`) — same EDL → same verdicts.
- **Render plan** (`render/segments.py`, `package/nle_export.py`) — same EDL → same cut list,
  same CMX3600 EDL, same subtitle timings.

These are guarded by unit + Hypothesis-fuzz tests and never vary run-to-run.

## Tier 2 — the editorial brain (pinned, two modes)

The cut decisions come from a language model, which is the only nondeterministic step. A **cloud**
brain (Claude/OpenAI) cannot be frozen, so:

- Every run **records the editorial model string** in `receipts.jsonl` and warns on drift.
- For a reproducible build, use the **local** brain (qwen via Ollama), pinned by **tag + digest**.

Local qwen has two reproducibility modes:

| Mode | Config | Output |
|------|--------|--------|
| **Quality (default)** | `temperature = 0.3`, `seed` unset | not bit-exact; the **golden suite** gates it to a tolerance band (duration, hook preservation, orphan count) |
| **Exact** | `temperature = 0`, `seed = <int>` | bit-exact editorial output for the same model digest + prompt |

To get exact reproducibility, in your eddy config:

```toml
[provider.ollama]
model = "qwen36-27b-codex:q4"
temperature = 0
seed = 42
```

Eddy then sends `options.seed` to Ollama, and qwen at `temperature=0` with a fixed seed produces the
same tokens every run on the same model digest.

## The golden suite is the GA gate

`tests/test_golden.py` (opt-in `EDDY_GOLDEN=1`) runs the **pinned local model** against frozen
transcript→cutplan fixtures and asserts the tolerance properties. v1.0 promotes it to a required GA
gate: a release is not cut unless the golden suite is green on the pinned model. This proves the
quality-mode editorial brain stays within band; exact-mode (`seed`) proves the stronger bit-exact
property when a reproducible artifact is required (e.g. an audit or a regression bisect).

## What is NOT reproducible
- A cloud editorial brain (record-and-warn only — can't be frozen).
- Anything depending on wall-clock time (stamped after the run, never inside decisions).
- A different model **digest** — `qwen…:q4` must resolve to the same blob; a re-pull that changes
  the digest can change output even at `temperature=0`.
