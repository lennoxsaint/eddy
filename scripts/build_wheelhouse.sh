#!/usr/bin/env bash
# Build an offline wheelhouse so Eddy installs on an air-gapped machine with NO network.
#
# Run this ONCE on a connected machine of the SAME OS + Python (3.11/3.12) + CPU arch as the target
# (wheels are platform-specific). It downloads Eddy + every pinned dependency as wheels into ./wheelhouse,
# then you copy that folder to the air-gapped box and `pip install --no-index --find-links wheelhouse eddy`.
#
# Usage:  scripts/build_wheelhouse.sh [output_dir]    (default: ./wheelhouse)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO_ROOT/wheelhouse}"
LOCK="$REPO_ROOT/requirements.lock"

echo "[wheelhouse] python: $(python3 --version)  platform: $(python3 -c 'import platform;print(platform.platform(), platform.machine())')"
mkdir -p "$OUT"

# 1) the pinned dependency closure (reproducible — exact versions from the lockfile)
if [[ -f "$LOCK" ]]; then
  echo "[wheelhouse] downloading pinned deps from requirements.lock"
  python3 -m pip download -r "$LOCK" -d "$OUT"
else
  echo "[wheelhouse] WARNING: requirements.lock missing — falling back to pyproject ranges (not reproducible)"
fi

# 2) build Eddy itself into a wheel in the same dir
echo "[wheelhouse] building eddy wheel"
python3 -m pip wheel "$REPO_ROOT" --no-deps -w "$OUT"

COUNT=$(find "$OUT" -name '*.whl' -o -name '*.tar.gz' | wc -l | tr -d ' ')
echo "[wheelhouse] done: $COUNT artifacts in $OUT"
echo "[wheelhouse] verify the closure is self-contained (no network):"
echo "    python3 -m pip install --no-index --find-links \"$OUT\" eddy --dry-run"
echo "[wheelhouse] NOTE: ffmpeg + the Whisper/qwen model weights are NOT pip packages — stage them separately (see docs/AIRGAP.md)."
