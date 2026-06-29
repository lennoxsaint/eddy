"""HyperFrames `frame.md` contract support.

HyperFrames' creative skill treats lowercase `frame.md` as the normative video-frame design
system, ahead of `design.md` and `DESIGN.md`. Eddy mirrors that rule for premium overlays.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

SPEC_PRECEDENCE = ("frame.md", "design.md", "DESIGN.md")
DEFAULT_SKILLS = (
    "hyperframes",
    "hyperframes-cli",
    "motion-graphics",
    "graphic-overlays",
    "product-launch-video",
    "hyperframes-core",
    "hyperframes-animation",
    "hyperframes-media",
)
DEFAULT_REGISTRY_PREFIXES = (
    "blocks/transitions",
    "blocks/product-promo",
    "blocks/flowchart",
    "blocks/code-",
    "blocks/vfx-liquid",
    "blocks/data-chart",
    "components/caption-",
    "components/highlight",
    "components/liquid",
    "components/morph",
    "components/shimmer",
    "components/texture",
)


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


def write_creator_good_frame(out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "frame.md"
    path.write_text(
        """---
frame_name: Eddy Creator-Good First-60
canvas: "1920x1080"
background: "transparent"
foreground: "#F7F8FB"
accent_primary: "#37FF8B"
accent_warning: "#FF4D4D"
accent_secondary: "#39BDF8"
typeface: "Inter"
motion_style: ["kinetic hook labels", "screen-safe proof overlays", "subtle launch motion"]
forbidden: ["covering face", "covering screen proof", "covering captions", "generic decorative blobs"]
---

# Eddy Creator-Good First-60

This frame is for the first 30-60 seconds of a default Eddy YouTube edit. It must reinforce the
spoken hook with compact proof labels, directional rails, and lightweight motion without obscuring
the camera PiP, screen content, captions, or proof UI.
"""
    )
    return path


def hyperframes_commit(hyperframes_root: Path) -> str:
    root = Path(hyperframes_root)
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
    except Exception:
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "unknown"


def index_hyperframes_assets(hyperframes_root: Path) -> dict:
    root = Path(hyperframes_root)
    registry = root / "registry"
    skills = root / "skills"
    assets: list[dict] = []
    for base in (registry, skills):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.name not in {".DS_Store"}:
                rel = path.relative_to(root)
                assets.append({
                    "path": str(rel),
                    "kind": rel.parts[0],
                    "name": rel.parts[-2] if len(rel.parts) > 2 else rel.stem,
                    "bytes": path.stat().st_size,
                })
    return {"hyperframes_root": str(root), "commit": hyperframes_commit(root), "asset_count": len(assets), "assets": assets}


def _selected_asset_paths(root: Path) -> list[Path]:
    selected: list[Path] = []
    for skill in DEFAULT_SKILLS:
        path = root / "skills" / skill
        if path.exists():
            selected.extend(p for p in path.rglob("*") if p.is_file())
    reg = root / "registry"
    if reg.exists():
        for path in reg.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(reg).as_posix()
            if any(rel.startswith(prefix) for prefix in DEFAULT_REGISTRY_PREFIXES):
                selected.append(path)
    return sorted(set(selected))


def write_hyperframes_cache(hyperframes_root: Path, cache_dir: Path) -> dict:
    root = Path(hyperframes_root)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    index = index_hyperframes_assets(root)
    (cache_dir / "hyperframes-pin.json").write_text(json.dumps({
        "hyperframes_root": str(root),
        "commit": index["commit"],
        "update_command": "eddy motion update-hyperframes",
        "update_policy": "explicit_notify_only",
    }, indent=2))
    (cache_dir / "registry-index.json").write_text(json.dumps(index, indent=2))
    return index


def copy_hyperframes_references(hyperframes_root: Path, dest: Path) -> dict:
    """Copy the selected per-run reference set for auditability; never hotlink the external repo."""
    root = Path(hyperframes_root)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    copies: list[dict] = []
    for src in _selected_asset_paths(root):
        if not src.exists():
            copies.append({"source": str(src), "status": "missing"})
            continue
        rel = src.relative_to(root)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copies.append({"source": str(src), "copied_to": str(target), "status": "copied"})
    manifest = {
        "hyperframes_root": str(root),
        "hyperframes_commit": hyperframes_commit(root),
        "selection_policy": "selected_skills_and_registry_assets",
        "copied": copies,
    }
    (dest / "copied-assets-manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def write_storyboard(out_dir: Path, frames: list[dict]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "storyboard.md"
    lines = ["# Storyboard", "", "Static contract before animation. Every beat needs a still frame proof."]
    for i, frame in enumerate(frames, start=1):
        lines += [
            "",
            f"## Frame {i}: {frame.get('title', f'Beat {i}')}",
            f"- time: `{frame.get('time', '')}`",
            f"- spoken beat: {frame.get('spoken_beat', '')}",
            f"- visual: {frame.get('visual', '')}",
            f"- safe zones: {frame.get('safe_zones', 'face, captions, proof UI, browser chrome')}",
            f"- transition: {frame.get('transition', 'fade/zoom/blur bridge')}",
        ]
    path.write_text("\n".join(lines) + "\n")
    return path


def write_storyboard_html(out_dir: Path, frames: list[dict]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for i, frame in enumerate(frames, start=1):
        cards.append(
            f"""
<section class="frame">
  <div class="meta">FRAME {i} · {frame.get('time', '')}</div>
  <h2>{frame.get('title', f'Beat {i}')}</h2>
  <p>{frame.get('visual', '')}</p>
  <div class="safe">SAFE: {frame.get('safe_zones', 'face · captions · proof UI · chrome')}</div>
</section>"""
        )
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Eddy Motion Storyboard</title>
  <style>
    :root {{ color-scheme: dark; --bg:#070A0F; --fg:#F7F8FB; --lime:#37FF8B; --red:#FF4D4D; --blue:#39BDF8; }}
    body {{ margin:0; background:var(--bg); color:var(--fg); font:24px Inter, Arial, sans-serif; }}
    main {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(480px,1fr)); gap:24px; padding:32px; }}
    .frame {{ aspect-ratio:16/9; border:3px solid var(--lime); background:linear-gradient(135deg,#07110C,#0B111C); padding:36px; box-sizing:border-box; position:relative; overflow:hidden; }}
    .frame:after {{ content:""; position:absolute; inset:auto 28px 28px auto; width:180px; height:4px; background:var(--blue); box-shadow:-220px -120px 0 var(--red); }}
    .meta {{ color:var(--lime); font-size:18px; letter-spacing:0; font-weight:800; }}
    h2 {{ font-size:56px; line-height:1; margin:48px 0 20px; max-width:780px; }}
    p {{ max-width:860px; line-height:1.2; color:#DDE3EA; }}
    .safe {{ position:absolute; left:36px; bottom:30px; color:#8EA0B2; font-size:18px; }}
  </style>
</head>
<body><main>{''.join(cards)}</main></body>
</html>
"""
    path = out_dir / "storyboard.html"
    path.write_text(html)
    return path


def build_threadify_motion_contract(project_dir: Path, hyperframes_root: Path) -> dict:
    motion_dir = Path(project_dir) / "post-production" / "hyperframes-motion"
    frame = write_threadify_proof_frame(motion_dir)
    frames = [
        {"time": "0:00-0:06", "title": "Most creators stop at publish", "visual": "Kinetic proof label enters from the left, receipt rail wakes up.", "spoken_beat": "hook"},
        {"time": "0:06-0:18", "title": "The loop finds hand raises", "visual": "Comment signal cards stack, then compress into one lead-loop rail.", "spoken_beat": "promise"},
        {"time": "0:18-0:35", "title": "You approve before send", "visual": "Approval gate locks in lime, no auto-send overclaim.", "spoken_beat": "control"},
        {"time": "0:35-0:60", "title": "Clicks read back to posts", "visual": "Receipt counter resolves to tracked CTA proof.", "spoken_beat": "proof"},
    ]
    storyboard = write_storyboard(motion_dir, frames)
    storyboard_html = write_storyboard_html(motion_dir, frames)
    vendor = motion_dir / "vendor" / "hyperframes"
    manifest = copy_hyperframes_references(hyperframes_root, vendor)
    return {
        "frame_spec": str(frame),
        "storyboard": str(storyboard),
        "storyboard_html": str(storyboard_html),
        "tokens": parse_frontmatter(frame),
        "copied_assets_manifest": str(vendor / "copied-assets-manifest.json"),
        "copied_assets": manifest["copied"],
    }
