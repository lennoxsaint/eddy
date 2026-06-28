# AGENTS.md — Eddy operating instructions

Eddy is a local-first agentic video editor: raw footage in → complete YouTube launch kit out.
This file governs every agent working in this repo.

## Hard gates (non-negotiable)

- **Never edit, delete, move, upload, publish, or transform source video files.** Inputs are read-only; `runs.py` hash-verifies sources before and after every run. All outputs go inside `runs/<run>/`.
- **No publishing or uploading anywhere, ever, without explicit manual invocation.** Eddy contains no publish code by design.
- **The repo is the public canonical Eddy editor (`origin` = `lennoxsaint/eddy`), trunk-based on `main`.** Commit and push straight to `main` after tests and the public scrub pass — no PRs, no feature-branch ceremony. Do NOT publish a package (PyPI / marketplace), send external messages, upload videos, or start new paid API jobs without explicit approval from Lennox. The only authorized paid APIs are Gemini + OpenAI image generation for thumbnails, cost-logged per call.
- **Do not claim Eddy "fully edits video" until the exact pipeline and quality gates are proven** with receipts on real footage.
- **Never edit `vendor/yt_tools/`.** Vendored originals are the diff anchor for every port.

## How to work here

- Source truth ranking: current repo files/receipts > docs > memory. Read before acting.
- If `AGENTS.local.md` exists, read it after this file for machine-local maintainer notes. It must never override these hard gates and must never contain secrets.
- When grilling Lennox with an ask-questions tool, ask exactly 3 useful questions at a time, with a recommended answer for each. Continue in 3-question packets until the spec is decision-complete, Lennox pauses the session, or a real blocker appears.
- Every model call, ffmpeg command, gate verdict, and ranking decision must land in the run's `receipts.jsonl`. No silent work.
- The build board, when available, is Linear team **EDD**, project **Eddy v1** (`scripts/linear.py`, needs `LINEAR_API_KEY`). Public contributors do not need Linear.
- **Git workflow (trunk-based):** small, frequent commits straight to `main`, then `git push origin main` as you go. No PRs. Tag releases (`git push origin --tags`) — tag pushes trigger the 3-OS CI matrix; `ci.yml` runs lint+types+tests on every push. Keep CI green; the local suite + ruff + mypy are the pre-push gate.
- Durable product/architecture decisions go in `docs/decision-log.md` (dated). Source-truth findings go in `docs/research-notes.md`.

## Risk-tiered trunk workflow

- **Low risk**: docs, tests, local maintainer guidance, comments, and internal cleanup with no product behavior change. Read back the touched files, run the relevant lightweight check, run `python3 scripts/public_scrub_check.py`, then `git diff --check`.
- **Medium risk**: product behavior, provider routing, render logic, MCP/tool behavior, config, packaging, and test changes. Run focused tests first, then `ruff check src tests`, `mypy src/eddy`, `pytest -q --cov=eddy --cov-report=term-missing`, `python3 scripts/public_scrub_check.py`, and `git diff --check` before pushing to `main`.
- **High risk**: source-media handling, destructive cleanup, privacy/egress boundaries, paid API jobs, release tags, plugin/public sharing, public claims, production/external side effects, or anything that could upload/publish/send. Get explicit Lennox approval for the high-risk action, keep a rollback path when practical, and follow the full local/release gates in `docs/RELEASE.md`.

Proof states are separate. Do not flatten local tests, public scrub, CI green, 3-OS matrix green, tag pushed, plugin installed, real-footage dogfood, and public distribution into the same claim. Say exactly which layer is proven and which layer is still pending.

## Map

- `docs/PRD.md` — the product contract. `docs/references/` — approved shorts rendering standard.
- `src/eddy/` — the app. `prompts/` — versioned prompt files. `tests/` — pytest (compiler/schema/gate logic).
- `vendor/yt_tools/` — read-only historical originals used as port references. `runs/` — per-video run artifacts (gitignored).
- `work/` — scratch. `scripts/` — build/board tooling.

## Verified commands

- `.venv/bin/eddy --help` — CLI
- `.venv/bin/pytest` — tests
- `.venv/bin/python scripts/linear.py list` — board state
- `ruff check src tests` — lint gate
- `mypy src/eddy` — type gate
- `pytest -q --cov=eddy --cov-report=term-missing` — full local suite with coverage floor
- `python3 scripts/public_scrub_check.py` — public-safe tracked-file scrub
- `git diff --check` — whitespace/conflict-marker check
