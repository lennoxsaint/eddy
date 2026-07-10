# Release process

Eddy has two update channels:

- Owner Claude/Codex installations symlink to canonical `main`.
- Plugin and external installations update atomically to immutable stable tags.

## Required green before v3.0.0

1. `ruff check src tests scripts`
2. `mypy src/eddy`
3. `pytest -q --cov=eddy --cov-report=term-missing` with coverage at or above the configured floor
4. `python scripts/sync_skill_surfaces.py --check`
5. `python scripts/public_scrub_check.py`
6. Synthetic full pipeline: three longs, three Shorts, motion, captions, audio gate, QA, source lock
7. Real calibration: failed Descript API export is red; owner-approved Descript reference is green
8. Five unique green owner-approved real-footage rows in `dogfood/trust-ledger.json`
9. Clean plugin install from the release tag and verified rollback to the previous working install

No stable tag is cut while any gate is red. The fake Descript and fake HyperFrames modes are test
fixtures only and never count as a real dogfood or release proof.

## Repository replacement

Before the identity swap, preserve the dirty legacy checkout, add a migration pointer to its README,
rename it `eddy-legacy`, and archive it. Then rename this repository to `eddy`, make it public, update
every explicit URL/action/remote, apply branch protection, and only then publish `v3.0.0` after the
required gates. Do not rely on GitHub redirects because the old repository name is being reused.

