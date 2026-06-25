# Release process

Eddy is versioned from git tags (`v0.4`...`v1.10.0`); the runtime version resolves via
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

For a controlled Codex Club beta, share the GitHub repo link plus the one-sentence Codex plugin
install prompt from [`CODEX_INSTALL.md`](CODEX_INSTALL.md):

```text
@plugin-creator install [lennoxsaint/eddy](https://github.com/lennoxsaint/eddy)
```

That path installs `plugins/eddy/`, which bundles the skill and MCP config. The plugin wrapper then
installs the latest stable Eddy tag into `~/.eddy/source` + `~/.eddy/venv`, smoke-checks it, and only
then swaps it active. Stable tag updates are automatic; `main` is never auto-installed.

The local skill+MCP fallback still exists:

```bash
python3 scripts/install_codex.py
```

It installs the skill plus MCP from the checkout and records exact blockers. The plugin path is
acceptable for a supervised 100-user beta only after:

1. `CI` and `CI matrix (3-OS)` are green on `main`;
2. `python3 scripts/public_scrub_check.py` passes;
3. `python3 scripts/install_codex_plugin.py --dry-run --json --ref vX.Y.Z` passes;
4. `python3 scripts/install_codex.py --dry-run --json` passes for fallback installs;
5. `eddy bootstrap --json` reports ready or exact repair steps on the maintainer machine;
6. public copy says “finished edit or exact blockers,” not “guaranteed perfect on every machine.”

Recommended non-plugin source install command for a green tagged release:

```bash
pipx install "eddy[mcp] @ git+https://github.com/lennoxsaint/eddy.git@v1.10.0"
```

Before a fresh tag exists, smoke-test the live branch with:

```bash
pipx install "eddy[mcp] @ git+https://github.com/lennoxsaint/eddy.git@main"
```

## Updates

Codex plugin users auto-update to the latest stable tag through the plugin bootstrapper. The active
state and failed-update blockers are written to:

```text
~/.eddy/plugin-state.json
```

Manual skill/MCP users update with:

```bash
git -C ~/eddy pull && pipx reinstall eddy
```

`eddy update-check` remains notify-only for manual checkouts.

## Rollback

Tags are immutable checkpoints. To roll back the global binary to a prior release:

```bash
git -C ~/eddy checkout vX.Y && pipx reinstall eddy
```
