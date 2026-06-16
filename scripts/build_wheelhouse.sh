#!/usr/bin/env bash
# Build an offline wheelhouse so Eddy installs on an air-gapped machine with NO network.
#
# Default: builds for THIS machine's OS + arch. With --target you can build a wheelhouse for a
# DIFFERENT platform from one connected machine (e.g. stage a Linux box from your Mac) — pip fetches
# the target's wheels by platform tag, so onnxruntime/numpy/av come down for the right arch instead
# of your host's. Python is pinned to one minor (3.11/3.12) because wheels are version-specific.
#
# Usage:
#   scripts/build_wheelhouse.sh [output_dir] [--target HOST] [--python 312]
#     output_dir   where to write wheels        (default: ./wheelhouse)
#     --target     host (default) | linux | windows | macos-arm | macos-x86
#     --python     CPython minor as digits      (default: 312 -> cp312)
#
# Then copy output_dir to the air-gapped box and:
#   pip install --no-index --find-links wheelhouse eddy
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$REPO_ROOT/requirements.lock"

OUT=""
TARGET="host"
PYVER="312"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2 ;;
    --python) PYVER="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
    -*) echo "[wheelhouse] unknown flag: $1" >&2; exit 2 ;;
    *) OUT="$1"; shift ;;
  esac
done
OUT="${OUT:-$REPO_ROOT/wheelhouse}"

# Cross-platform download flags by target. manylinux gets two tags (2_17 == 2014) so more wheels
# match. An empty array = build for the host (pip auto-selects this machine's tags).
PLAT_ARGS=()
case "$TARGET" in
  host) ;;
  linux)     PLAT_ARGS=(--platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64) ;;
  windows)   PLAT_ARGS=(--platform win_amd64) ;;
  macos-arm) PLAT_ARGS=(--platform macosx_11_0_arm64) ;;
  macos-x86) PLAT_ARGS=(--platform macosx_10_9_x86_64) ;;
  *) echo "[wheelhouse] unknown --target '$TARGET' (host|linux|windows|macos-arm|macos-x86)" >&2; exit 2 ;;
esac
if [[ "$TARGET" != "host" ]]; then
  # a foreign target can't build sdists, so pin the interpreter and force real wheels
  PLAT_ARGS+=(--python-version "$PYVER" --implementation cp --abi "cp${PYVER}")
fi

echo "[wheelhouse] host python: $(python3 --version)  host platform: $(python3 -c 'import platform;print(platform.platform(), platform.machine())')"
echo "[wheelhouse] target: $TARGET  python: cp${PYVER}  ->  $OUT"
mkdir -p "$OUT"

# 1) the pinned dependency closure (reproducible — exact versions from the lockfile).
#    --only-binary=:all: forces real platform WHEELS: if one is missing for the target OS/arch the
#    build fails HERE (on the connected machine) instead of silently shipping an sdist that needs a
#    compiler + headers on the air-gapped box (which would defeat the no-network promise).
if [[ -f "$LOCK" ]]; then
  echo "[wheelhouse] downloading pinned deps (wheels only) from requirements.lock"
  python3 -m pip download --only-binary=:all: "${PLAT_ARGS[@]}" -r "$LOCK" -d "$OUT"
else
  echo "[wheelhouse] WARNING: requirements.lock missing — falling back to pyproject ranges (not reproducible)"
fi

# 2) build Eddy itself into a wheel in the same dir. Eddy is pure-Python, so its wheel is
#    py3-none-any and installs on every target regardless of where it was built.
echo "[wheelhouse] building eddy wheel (pure-python, cross-platform)"
python3 -m pip wheel "$REPO_ROOT" --no-deps -w "$OUT"

COUNT=$(find "$OUT" -name '*.whl' -o -name '*.tar.gz' | wc -l | tr -d ' ')
echo "[wheelhouse] done: $COUNT artifacts in $OUT"
echo "[wheelhouse] verify the closure is self-contained (no network):"
echo "    python3 -m pip install --no-index --find-links \"$OUT\" eddy --dry-run"
echo "[wheelhouse] NOTE: ffmpeg + the Whisper/qwen model weights are NOT pip packages — stage them separately (see docs/AIRGAP.md)."
