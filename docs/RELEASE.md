# Release process

Eddy has two update channels:

- Owner Claude/Codex installations symlink to canonical `main`.
- Plugin and external installations update atomically to immutable stable tags.

## V3.0.0 release record

The release requires:

1. `ruff check src tests scripts`;
2. `mypy src/eddy`;
3. `pytest -q --cov=eddy --cov-report=term-missing` at or above the coverage floor;
4. `python scripts/sync_skill_surfaces.py --check`;
5. `python scripts/public_scrub_check.py`;
6. synthetic three-Long/three-Short pipeline coverage;
7. a clean plugin install from the immutable release tag and a verified rollback path;
8. successful Linux, macOS, and Windows tag CI.

On 2026-07-29, Lennox explicitly authorized V3 publication and `v3.0.0` despite the trust verifier
reporting `0/5` proof-backed owner runs. That owner exception waives only the publication timing
gate. The five-run gate still controls the separate claim that Eddy is safe to publish without
human review. Fake Descript and fake HyperFrames modes remain fixtures and never become dogfood
proof.

## Repository replacement

Preserve the dirty legacy checkout, add a migration pointer to its README from a clean clone, rename
it `eddy-legacy`, and archive it. Then rename this repository to `eddy`, make it public, update every
explicit URL/action/remote, apply branch protection, and publish `v3.0.0`. Do not rely on GitHub
redirects because the old repository name is reused.
