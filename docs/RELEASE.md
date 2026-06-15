# Release process

Eddy is versioned from git tags (`v0.4`…`v1.0`); the runtime version resolves via
`importlib.metadata` / git-describe and is stamped into run receipts. Releases are cut locally and —
once the private remote + signing certs exist (human-gate) — published.

## Required-green gate (before any tag)

A tag is cut ONLY when all of these are green on the release commit:

1. `ruff check src tests` — clean.
2. `mypy src/eddy` — clean.
3. `pytest -q --cov=eddy` — full suite green AND coverage ≥ the floor in `[tool.coverage.report]`
   (fails the build if it regresses).
4. `EDDY_GOLDEN=1 pytest tests/test_golden.py` — the golden editorial suite green on the **pinned**
   local model (qwen `:q4`). This is the GA reproducibility gate.
5. The 3-OS CI matrix (`.github/workflows/ci-matrix.yml`) green — proves Windows/Linux/macOS once
   the remote exists. Until then it is authored + locally-validated on macOS and marked CI-pending.

No tag on assertion alone — the suite + golden + matrix must actually pass.

## Cutting a release (local)

```bash
# 1. all gates green (above)
# 2. bump version in pyproject.toml
# 3. ff-merge the milestone branch to master, then:
git tag vX.Y
pipx reinstall eddy          # update the global binary from the working tree
eddy --version               # confirm the new version
```

The repo does **not** push by default (per AGENTS.md). Pushing + publishing is a human-gate step.

## Signed / notarized artifacts (HUMAN-GATE)

Distribution requires credentials Eddy cannot self-provision:

- **macOS**: Apple Developer ID signing + notarization (`codesign` + `notarytool`). Requires an
  Apple Developer account (~$99/yr).
- **Windows**: Authenticode signing of the installer/exe. Requires a code-signing certificate.
- **PyPI / private index**: an account + API token to publish the wheel.

Until those exist, the supported install paths are: `pipx install` from the source tree, or the
offline wheelhouse (`docs/AIRGAP.md`).

## Update check

There is no auto-updater (no remote yet). Users update with:

```bash
pipx upgrade eddy            # from a configured index, once published
# or, from source:
git -C ~/eddy pull && pipx reinstall eddy
```

`eddy --version` shows the installed version; compare against the latest tag. An in-app update
check is deferred until the publish channel is authorized (human-gate).

## Rollback

Tags are immutable checkpoints. To roll back the global binary to a prior release:

```bash
git -C ~/eddy checkout vX.Y && pipx reinstall eddy
```
