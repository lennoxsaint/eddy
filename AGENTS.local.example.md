# AGENTS.local.md example

Copy this file to `AGENTS.local.md` for machine-local maintainer notes. The real file is ignored by git.

Rules:

- Never put API keys, tokens, passwords, private keys, or credential values here.
- Local notes may clarify paths, proof habits, and maintainer-only setup, but they never override `AGENTS.md`.
- Keep source media read-only. Record exact run paths and blockers instead of moving or rewriting inputs.

Suggested sections:

## Local Paths

- Checkout: `/path/to/eddy`
- Runs: `~/.eddy/runs/`
- Optional scratch: `work/`

## Proof Habits

- For docs-only maintainer guidance, read back touched files, run `python3 scripts/public_scrub_check.py`, and run `git diff --check`.
- For code changes, run a focused test first, then the full gate listed in `AGENTS.md`.
- Keep proof states separate: local check, CI, tag, plugin install, and real-footage dogfood are different claims.

## Local Services

- Linear uses `LINEAR_API_KEY` from the local environment or ignored secret setup. Do not write the value here.
- Second Brain logging, if required by the active instructions, must use the canonical gateway script rather than direct markdown writes.

## Dogfood Handles

- Record only handles, slugs, and read-only source locations that are safe for future maintainers to know.
- Do not paste transcripts, raw private footage metadata, or credential-bearing URLs.
