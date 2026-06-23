"""HyperFrames `frame.md` contract support.

HyperFrames' creative skill treats lowercase `frame.md` as the normative video-frame design
system, ahead of `design.md` and `DESIGN.md`. Eddy mirrors that rule for premium overlays.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

SPEC_PRECEDENCE = ("frame.md", "design.md", "DESIGN.md")


def find_frame_spec(root: Path) -> Path | None:
    root = Path(root)
    for name in SPEC_PRECEDENCE:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def parse_frontmatter(path: Path) -> dict:
    text = Path(path).read_text()
    if not text.startswith("---\n"):
        return {}
    try:
        block = text.split("---", 2)[1]
    except IndexError:
        return {}
    out: dict = {}
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
            out[key.strip()] = items
        else:
            out[key.strip()] = value
    return out


def write_threadify_proof_frame(out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "frame.md"
    path.write_text(
        """---
frame_name: Threadify Proof Frame
canvas: "1920x1080"
background: "#070A0F"
foreground: "#F7F8FB"
accent_primary: "#37FF8B"
accent_warning: "#FF4D4D"
accent_secondary: "#39BDF8"
typeface: "Inter"
motion_style: ["kinetic proof labels", "process frame", "screen-safe overlays"]
forbidden: ["generic SaaS gradient", "blurred private data", "covering face", "covering proof UI"]
---

# Threadify Proof Frame

This frame is for the first 30-60 seconds of a Threadify lead-loop video. It should feel like
a premium proof system, not a drawn flowchart. Use dark/lime proof aesthetics, compact kinetic
type, thin technical dividers, receipt-style counters, and screen-safe callouts.

Motion must complement the spoken hook and never cover the camera bubble, browser chrome, live
proof UI, captions, chat input, or any text the viewer needs to read. If a collision is detected,
redesign the overlay rather than promoting it.
"""
    )
    return path


def copy_hyperframes_references(hyperframes_root: Path, dest: Path) -> dict:
    """Copy a minimal local reference set for auditability; never hotlink the external repo."""
    root = Path(hyperframes_root)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    copies: list[dict] = []
    wanted = [
        root / "skills" / "hyperframes-creative" / "references" / "design-spec.md",
        root / "skills" / "hyperframes-creative" / "references" / "video-composition.md",
        root / "skills" / "hyperframes-creative" / "references" / "house-style.md",
        root / "skills" / "hyperframes-creative" / "frame-presets" / "creative-mode" / "FRAME.md",
        root / "skills" / "hyperframes-creative" / "frame-presets" / "blockframe" / "FRAME.md",
    ]
    for src in wanted:
        if not src.exists():
            copies.append({"source": str(src), "status": "missing"})
            continue
        rel = src.relative_to(root)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copies.append({"source": str(src), "copied_to": str(target), "status": "copied"})
    manifest = {"hyperframes_root": str(root), "copied": copies}
    (dest / "copied-assets-manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def build_threadify_motion_contract(project_dir: Path, hyperframes_root: Path) -> dict:
    motion_dir = Path(project_dir) / "post-production" / "hyperframes-motion"
    frame = write_threadify_proof_frame(motion_dir)
    vendor = motion_dir / "vendor" / "hyperframes"
    manifest = copy_hyperframes_references(hyperframes_root, vendor)
    return {
        "frame_spec": str(frame),
        "tokens": parse_frontmatter(frame),
        "copied_assets_manifest": str(vendor / "copied-assets-manifest.json"),
        "copied_assets": manifest["copied"],
    }
