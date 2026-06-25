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
4. `EDDY_GOLDEN=1 pytest tests/test_golden.py` — maintainer-local proof that the golden editorial
   suite is green on the **pinned** local model (qwen `:q4`). GitHub CI does not run this slow
   hardware/model gate; record the local command output in the release notes before sharing.
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

Until those exist, the supported install paths are GitHub-source installs, editable installs from a
clone, or the offline wheelhouse (`docs/AIRGAP.md`). Do not document bare index installs for Eddy or
its MCP extra until the package name is owned; the public PyPI name currently belongs to another
project.

## Codex Club / 100-user beta share path

For a controlled Codex Club beta, share the GitHub repo link plus the one-sentence Codex install
prompt from [`CODEX_INSTALL.md`](CODEX_INSTALL.md). That path clones the repo and runs:

```bash
python3 scripts/install_codex.py
```

This is different from a polished package release. It installs the skill plus MCP from the checkout
and records exact blockers. It is acceptable for a supervised 100-user beta only after:

1. `CI` and `CI matrix (3-OS)` are green on `main`;
2. `python3 scripts/public_scrub_check.py` passes;
3. `python3 scripts/install_codex.py --dry-run --json` passes;
4. `eddy bootstrap --json` reports ready or exact repair steps on the maintainer machine;
5. public copy says “finished edit or exact blockers,” not “guaranteed perfect on every machine.”

Recommended public install command for a green tagged release:

```bash
pipx install "eddy[mcp] @ git+https://github.com/lennoxsaint/eddy.git@v1.9.1"
```

Before a fresh tag exists, smoke-test the live branch with:

```bash
pipx install "eddy[mcp] @ git+https://github.com/lennoxsaint/eddy.git@main"
```

## Update check

There is no auto-updater. Users update with:

```bash
git -C ~/eddy pull && pipx reinstall eddy
```

`eddy --version` shows the installed version; compare against the latest tag. An in-app update
check is deferred until a package channel exists.

## Rollback

Tags are immutable checkpoints. To roll back the global binary to a prior release:

```bash
git -C ~/eddy checkout vX.Y && pipx reinstall eddy
```
