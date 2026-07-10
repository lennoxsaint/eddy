"""Hash and project the one canonical Eddy package into platform bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CANONICAL_SURFACES = (
    "SKILL.md",
    "README.md",
    "assets/fonts/Montserrat.ttf",
    "assets/vendor/gsap.min.js",
    "assets/motion/threadify-fc/frame.md",
    "assets/motion/threadify-fc/font-face.css",
    "assets/motion/threadify-fc/identity.css",
    "assets/motion/threadify-fc/assets/fc-ring.png",
    "assets/motion/threadify-fc/assets/threadify-needle.png",
    "evals/evals.json",
    "references/commands.md",
    "references/edit-plan-schema.md",
    "references/hook-doctrine.md",
    "references/layout-constants.md",
    "references/motion-layer.md",
    "references/retention-policy.md",
    "references/sop.md",
    "references/verification.md",
    "scripts/composite_render.py",
    "scripts/descript_studio_sound.py",
    "scripts/karaoke_ass.py",
    "scripts/motion_render.py",
    "scripts/motion_type.py",
    "scripts/splice.py",
    "scripts/transcribe.py",
    "scripts/verify.py",
)


@dataclass(frozen=True, slots=True)
class ProjectionCheck:
    ok: bool
    missing: tuple[str, ...]
    changed: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    root: Path,
    *,
    canonical_commit: str,
    files: Iterable[str] = CANONICAL_SURFACES,
) -> dict[str, object]:
    hashes = {relative: _sha256(root / relative) for relative in files}
    return {
        "schema_version": "eddy-surface-manifest-v1",
        "canonical_commit": canonical_commit,
        "files": hashes,
    }


def check_projection(
    source: Path,
    projection: Path,
    *,
    files: Iterable[str] = CANONICAL_SURFACES,
) -> ProjectionCheck:
    missing: list[str] = []
    changed: list[str] = []
    for relative in files:
        expected = source / relative
        actual = projection / relative
        if not actual.exists():
            missing.append(relative)
        elif _sha256(expected) != _sha256(actual):
            changed.append(relative)
    return ProjectionCheck(not missing and not changed, tuple(missing), tuple(changed))


def write_projection(
    source: Path,
    projection: Path,
    *,
    canonical_commit: str,
    files: Iterable[str] = CANONICAL_SURFACES,
) -> Path:
    selected = tuple(files)
    for relative in selected:
        destination = projection / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    manifest = build_manifest(source, canonical_commit=canonical_commit, files=selected)
    manifest_path = projection / "eddy-surface-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path
