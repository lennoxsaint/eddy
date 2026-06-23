# Release process

Eddy is versioned from git tags (`v0.4`...`v1.0`); the runtime version resolves via
`importlib.metadata` / git-describe and is stamped into run receipts. The canonical repo is
`https://github.com/lennoxsaint/eddy`.

## Required-green gate (before any tag)

A tag is cut ONLY when all of these are green on the release commit:

1. `ruff check src tests` — clean.
2. `mypy src/eddy` — clean.
3. `pytest -q --cov=eddy` — full suite green AND coverage ≥ the floor in `[tool.coverage.report]`
   (fails the build if it regresses).
4. `EDDY_GOLDEN=1 pytest tests/test_golden.py` — the golden editorial suite green on the **pinned**
   local model (qwen `:q4`). This is the GA reproducibility gate.
5. The 3-OS CI matrix (`.github/workflows/ci-matrix.yml`) green when release packaging is in scope.
   Local source edits must at minimum pass the focused tests plus the public scrub check before push.

No tag on assertion alone — the suite + golden + matrix must actually pass.

## Cutting a release (local)

```bash
# 1. all gates green (above)
# 2. bump version in pyproject.toml
# 3. merge the milestone branch to main, then:
git tag vX.Y
pipx reinstall eddy          # update the global binary from the working tree
eddy --version               # confirm the new version
```

Commit and push normal source changes to `main` after tests and the public scrub pass. Publishing a
package or installer remains a separate explicit action.

## Signed / notarized artifacts

Distribution requires credentials Eddy cannot self-provision:

- **macOS**: Apple Developer ID signing + notarization (`codesign` + `notarytool`). Requires an
  Apple Developer account (~$99/yr).
- **Windows**: Authenticode signing of the installer/exe. Requires a code-signing certificate.
- **PyPI / private index**: an account + API token to publish the wheel.

Until those exist, the supported install paths are: `pipx install` from source, editable install
from the public GitHub repo, or the offline wheelhouse (`docs/AIRGAP.md`).

## Update check

There is no auto-updater. Users update with:

```bash
pipx upgrade eddy            # from a configured index, once published
# or, from source:
git -C ~/eddy pull && pipx reinstall eddy
```

`eddy --version` shows the installed version; compare against the latest tag. An in-app update
check is deferred until a package channel exists.

## Rollback

Tags are immutable checkpoints. To roll back the global binary to a prior release:

```bash
git -C ~/eddy checkout vX.Y && pipx reinstall eddy
```
