#!/usr/bin/env python3
"""Motion render — on-brand HyperFrames motion (the DEFAULT motion engine).

Two modes, both render through eddy-v2's HyperFrames node runner in the `threadify-fc` identity and
composite a keyed-alpha overlay onto a base clip. We REUSE the runner + identity; we never edit them.

  --brief brief.json  (PREFERRED, iconography-forward): build a CUSTOM icon/image-led index.html
      (SVG icons, provider chips, framed real screenshots, stat callouts, flow diagrams — minimal
      supporting text, NO "EDDY V2" watermark) and render it via the node runner directly. This is
      the "custom animated HTML layer" — icon-led, not text-led.
  --hook "text"       (FALLBACK): use eddy-v2's built-in text-led scaffolder (create_motion_project).

Motion is iconography/image-forward (references/motion-layer.md). The overlay's black areas are keyed
transparent so the base video shows through; the brand graphics ride on top.

MACHINE SAFETY (hard rule): the real render drives a headless Chromium via `npx hyperframes`. NEVER
run this concurrently with an ffmpeg encode — render motion FIRST, composite AFTER. Use `--fake` to
validate mechanics with zero GPU.

Brief schema (brief.json):
  {"width":1920,"height":1080,"duration":12.0,
   "beats":[
     {"start":0.0,"dur":4.0,"layout":"image","kicker":"THE RECEIPT","label":"46,000 views",
      "image":"/abs/post.png"},
     {"start":4.0,"dur":4.0,"layout":"chips","kicker":"ANY MODEL","chips":["GLM","Kimi","Qwen","DeepSeek"]},
     {"start":8.0,"dur":4.0,"layout":"icons","kicker":"LOCAL & FREE",
      "icons":[{"svg":"laptop","label":"local"},{"svg":"lock","label":"private"},{"svg":"free","label":"free"}]},
     {"start":.,"dur":.,"layout":"stat","kicker":"...","value":"46K","label":"views, not mine"},
     {"start":.,"dur":.,"layout":"flow","kicker":"HOW","nodes":["Duplicate Codex","Local proxy","Any model"]}
   ]}

Usage:
  motion_render.py --brief brief.json --run-dir work/mo --out overlay.mp4 \
      [--composite-over base.mp4 --composite-out out.mp4] [--portrait] [--fake]
  motion_render.py --hook "Codex with any model — free" --run-dir work/mo --out overlay.mp4 ...
"""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

EDDY_V2 = Path(os.path.expanduser("~/eddy-v2"))
V2_PY = EDDY_V2 / ".venv" / "bin" / "python"
V2_SRC = EDDY_V2 / "src"
NODE_RUNNER = EDDY_V2 / "renderer" / "hyperframes-runner.mjs"
IDENTITY_DIR = Path(os.path.expanduser("~/eddy/src/eddy/motion/identities/threadify-fc"))

# Key the black background out to alpha, then overlay (eddy-v2's composite recipe).
KEY = "colorkey=0x000000:0.10:0.12,colorchannelmixer=aa=0.94"

# --- inline stroke icons (viewBox 0 0 100 100, stroke=currentColor) -----------------------------
ICONS = {
    "laptop": '<path d="M22 30h56v34H22z"/><path d="M12 72h76l-6-8H18z"/>',
    "lock": '<rect x="26" y="46" width="48" height="36" rx="6"/><path d="M36 46v-10a14 14 0 0 1 28 0v10"/>',
    "free": '<circle cx="50" cy="50" r="34"/><path d="M50 30v40M40 40h16a8 8 0 0 1 0 16H40M40 60h20"/>',
    "swap": '<path d="M28 38h44l-12-12M72 62H28l12 12"/>',
    "bolt": '<path d="M56 14 30 54h18l-6 32 28-42H50z"/>',
    "download": '<path d="M50 20v36M36 44l14 14 14-14M26 74h48"/>',
    "chip": '<rect x="30" y="30" width="40" height="40" rx="4"/><path d="M40 20v10M60 20v10M40 70v10M60 70v10M20 40h10M20 60h10M70 40h10M70 60h10"/>',
    "cloud": '<path d="M32 66a16 16 0 0 1 2-32 20 20 0 0 1 38 6 14 14 0 0 1-2 26z"/>',
    "check": '<path d="M28 52l14 14 30-32"/>',
    "globe": '<circle cx="50" cy="50" r="32"/><path d="M18 50h64M50 18v64M28 30a44 44 0 0 0 44 0M28 70a44 44 0 0 1 44 0"/>',
}


def svg(name: str) -> str:
    body = ICONS.get(name, ICONS["check"])
    return (f'<svg viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="5" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def esc(t: str) -> str:
    return html.escape(str(t))


# --- custom icon-led HTML (the "custom animated HTML layer") ------------------------------------
_CSS = """
  @import url("./font-face.css");
  @import url("./identity.css");
  body { margin: 0; background: #000; }
  #stage { position: relative; overflow: hidden; background: #000; color: var(--text,#fafafa);
           font-family: var(--display); }
  .grain { position:absolute; inset:0; pointer-events:none; opacity:0.10; mix-blend-mode:screen; z-index:1;
    background-image: repeating-linear-gradient(0deg, rgba(255,255,255,0.07) 0 1px, transparent 1px 4px); }
  .ring { position:absolute; right:120px; bottom:96px; width:360px; height:360px; opacity:0.16; z-index:1; }
  .chrome { position:absolute; left:88px; right:88px; top:60px; display:flex; align-items:center;
    justify-content:space-between; font-family:var(--mono); letter-spacing:0.22em; font-weight:700;
    font-size:20px; color:var(--muted,#737373); z-index:8; }
  .chrome .b { display:flex; align-items:center; gap:14px; color:var(--text); }
  .chrome .b img { width:30px; height:30px; }
  .frameline { position:absolute; left:88px; right:88px; top:104px; height:2px; transform-origin:left center;
    background: linear-gradient(90deg, var(--accent,#FF0000), var(--panel-edge,#282626)); z-index:8; }
  .scene { position:absolute; inset:0; opacity:0; z-index:3; display:flex; align-items:center;
    justify-content:center; }
  .block { display:flex; flex-direction:column; align-items:center; gap:34px; text-align:center;
    padding:0 160px; box-sizing:border-box; max-width:100%; }
  .kicker { color:var(--accent,#FF0000); font-family:var(--mono); letter-spacing:0.26em;
    font-weight:700; font-size:26px; text-transform:uppercase; }
  .accent-rule { height:5px; width:150px; background:var(--accent,#FF0000); transform-origin:center; }
  .label { color:var(--text,#fafafa); font-family:var(--display); font-weight:900; font-size:56px;
    line-height:1.02; letter-spacing:-0.02em; max-width:1400px; }
  .row { display:flex; align-items:stretch; justify-content:center; gap:34px; flex-wrap:wrap; }
  .tile { display:flex; flex-direction:column; align-items:center; gap:18px; padding:34px 30px;
    min-width:210px; background: color-mix(in srgb, var(--panel,#141414) 88%, transparent);
    border:1px solid var(--panel-edge,#282626); border-top:6px solid var(--accent,#FF0000); }
  .tile .ic { width:120px; height:120px; color:var(--text); }
  .tile .cap { font-family:var(--mono); font-weight:700; font-size:26px; letter-spacing:0.08em;
    text-transform:uppercase; color:var(--text); }
  .chip { padding:22px 40px; font-family:var(--mono); font-weight:700; font-size:40px; letter-spacing:0.02em;
    color:var(--text); background: color-mix(in srgb, var(--panel,#141414) 90%, transparent);
    border:1px solid var(--panel-edge,#282626); border-left:6px solid var(--accent,#FF0000); }
  .stat { font-family:var(--display); font-weight:900; letter-spacing:-0.03em; color:var(--accent,#FF0000);
    font-size:300px; line-height:0.9; }
  .sub { font-family:var(--mono); font-weight:700; font-size:34px; letter-spacing:0.06em; color:var(--text);
    text-transform:uppercase; }
  .imgwrap { border:1px solid var(--panel-edge,#282626); border-top:8px solid var(--accent,#FF0000);
    background:var(--panel,#141414); padding:12px; box-shadow:0 26px 80px rgba(0,0,0,0.45); }
  .imgwrap img { display:block; max-width:1360px; max-height:760px; }
  .flow { display:flex; align-items:center; justify-content:center; gap:0; flex-wrap:nowrap; }
  .node { padding:30px 34px; font-family:var(--display); font-weight:900; font-size:40px; color:var(--text);
    background: color-mix(in srgb, var(--panel,#141414) 90%, transparent); border:1px solid var(--panel-edge,#282626);
    border-bottom:6px solid var(--accent,#FF0000); max-width:360px; }
  .arrow { color:var(--accent,#FF0000); font-family:var(--mono); font-weight:700; font-size:56px; padding:0 22px; }
"""


def _beat_markup(i: int, b: dict) -> str:
    layout = b.get("layout", "icons")
    kicker = f'<div class="kicker">{esc(b["kicker"])}</div>' if b.get("kicker") else ""
    rule = '<div class="accent-rule"></div>'
    if layout == "image":
        cap = f'<div class="label">{esc(b["label"])}</div>' if b.get("label") else ""
        inner = f'<div class="imgwrap"><img src="./img-{i}.png" alt=""/></div>{cap}'
    elif layout == "chips":
        chips = "".join(f'<div class="chip stagger">{esc(c)}</div>' for c in b.get("chips", []))
        inner = f'<div class="row">{chips}</div>'
    elif layout == "icons":
        tiles = "".join(
            f'<div class="tile stagger"><span class="ic">{svg(ic.get("svg","check"))}</span>'
            f'<span class="cap">{esc(ic.get("label",""))}</span></div>'
            for ic in b.get("icons", []))
        inner = f'<div class="row">{tiles}</div>'
    elif layout == "stat":
        sub = f'<div class="sub">{esc(b["label"])}</div>' if b.get("label") else ""
        inner = f'<div class="stat">{esc(b.get("value",""))}</div>{sub}'
    elif layout == "flow":
        parts = []
        for j, n in enumerate(b.get("nodes", [])):
            if j:
                parts.append('<span class="arrow stagger">&#8594;</span>')
            parts.append(f'<div class="node stagger">{esc(n)}</div>')
        inner = f'<div class="flow">{"".join(parts)}</div>'
    else:
        lbl = f'<div class="label">{esc(b.get("label",""))}</div>' if b.get("label") else ""
        inner = lbl
    return (f'<div id="scene-{i}" class="scene"><div class="block">'
            f'{kicker}{rule}{inner}</div></div>')


def _timeline(beats: list[dict]) -> str:
    lines = ["window.__timelines = window.__timelines || {};",
             "const tl = gsap.timeline({ paused: true });"]
    for i, b in enumerate(beats):
        s = float(b["start"]); d = float(b.get("dur", 4.0))
        lines += [
            f'tl.set("#scene-{i}", {{opacity:1}}, {s:.3f});',
            f'tl.from("#scene-{i} .block", {{y:64, opacity:0, duration:0.6, ease:"power3.out"}}, {s + 0.04:.3f});',
            f'tl.from("#scene-{i} .accent-rule", {{scaleX:0, duration:0.5, ease:"power3.out"}}, {s + 0.28:.3f});',
            f'tl.from("#scene-{i} .stagger", {{y:34, opacity:0, duration:0.42, stagger:0.12, ease:"back.out(1.3)"}}, {s + 0.34:.3f});',
            f'tl.to("#scene-{i} .block", {{y:-22, opacity:0, duration:0.34, ease:"power2.in"}}, {s + d - 0.34:.3f});',
            f'tl.set("#scene-{i}", {{opacity:0}}, {s + d:.3f});',
        ]
    lines.append('window.__timelines["eddy-v2"] = tl;')
    return "\n".join(lines)


def build_custom_html(brief: dict, needle_rel: str | None, ring_rel: str | None) -> str:
    w = int(brief.get("width", 1920)); h = int(brief.get("height", 1080))
    beats = brief.get("beats", [])
    dur = float(brief.get("duration") or max((float(b["start"]) + float(b.get("dur", 4.0)) for b in beats), default=6.0))
    brand = (f'<span class="b">'
             + (f'<img src="./{needle_rel}" alt=""/>' if needle_rel else "")
             + 'THREADIFY</span>')
    ring = f'<img class="ring" src="./{ring_rel}" alt="" data-layout-ignore>' if ring_rel else ""
    scenes = "\n".join(_beat_markup(i, b) for i, b in enumerate(beats))
    return f"""<!doctype html>
<html><head><meta charset="utf-8" />
<style>{_CSS}
  #stage {{ width:{w}px; height:{h}px; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
</head><body>
<div id="stage" data-composition-id="eddy-v2" data-start="0" data-duration="{dur:.3f}" data-track-index="0" data-width="{w}" data-height="{h}">
  <div class="grain" data-layout-ignore></div>
  {ring}
  <div class="chrome">{brand}<span>THREADIFY-FC</span></div>
  <div class="frameline" data-layout-ignore></div>
  {scenes}
</div>
<script>
{_timeline(beats)}
</script>
</body></html>
"""


def scaffold_custom_project(project: Path, brief: dict) -> float:
    project.mkdir(parents=True, exist_ok=True)
    # identity assets (frozen — copied, never edited)
    for f in ("identity.css", "font-face.css"):
        src = IDENTITY_DIR / f
        if src.exists():
            shutil.copy2(src, project / f)
        elif f == "font-face.css":
            (project / f).write_text("")  # optional import must resolve
    assets_dir = IDENTITY_DIR / "assets"
    needle_rel = ring_rel = None
    if (assets_dir / "threadify-needle.png").exists():
        shutil.copy2(assets_dir / "threadify-needle.png", project / "needle.png"); needle_rel = "needle.png"
    if (assets_dir / "fc-ring.png").exists():
        shutil.copy2(assets_dir / "fc-ring.png", project / "ring.png"); ring_rel = "ring.png"
    # copy per-beat images into the project (Chromium loads them relative)
    for i, b in enumerate(brief.get("beats", [])):
        img = b.get("image")
        if img and Path(img).exists():
            shutil.copy2(img, project / f"img-{i}.png")
    html_doc = build_custom_html(brief, needle_rel, ring_rel)
    (project / "index.html").write_text(html_doc, encoding="utf-8")
    return float(brief.get("duration") or max(
        (float(b["start"]) + float(b.get("dur", 4.0)) for b in brief.get("beats", [])), default=6.0))


def render_custom_node(project: Path, out: Path, fake: bool, w: int, h: int, dur: float) -> bool:
    """Render the custom project via the node runner directly (lint is warn-only; we skip eddy-v2's
    strict inspect gate so a bespoke layout isn't rejected). Returns True on success."""
    if fake:
        subprocess.run(["nice", "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"testsrc2=size={w}x{h}:rate=30:duration={dur}", "-vf",
                        "eq=brightness=-0.25:saturation=0.45", "-an", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(out)], check=False)
        return out.exists()
    lint = subprocess.run(["node", str(NODE_RUNNER), "lint", str(project), "--json"],
                          capture_output=True, text=True)
    (project / "motion-lint.json").write_text(lint.stdout or lint.stderr or "{}")
    r = subprocess.run(["node", str(NODE_RUNNER), "render", str(project),
                        "--quality", "draft", "--output", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        print((r.stderr or r.stdout)[-2500:], file=sys.stderr)
        return False
    return True


# --- eddy-v2 text scaffolder (fallback) ---------------------------------------------------------
_RUNNER = r"""
import shutil, sys
from pathlib import Path
from eddy_v2.motion import create_motion_project, run_hyperframes
from eddy_v2.receipts import Receipts

run_dir = Path(sys.argv[1]); identity = sys.argv[2]; hook = sys.argv[3]
portrait = sys.argv[4] == "1"; duration = float(sys.argv[5]); out_path = Path(sys.argv[6])
run_dir.mkdir(parents=True, exist_ok=True)
receipts = Receipts(run_dir / "motion-receipts.jsonl")
project = create_motion_project(run_dir, identity, hook, portrait=portrait,
                                duration_s=duration, plan=None, receipts=receipts)
overlay = run_hyperframes(project, receipts, portrait=portrait)
out_path.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(overlay, out_path)
print("OVERLAY " + str(out_path))
"""


def render_hook_scaffolder(run_dir: str, identity: str, hook: str, portrait: bool,
                           duration: float, out: Path, fake: bool) -> bool:
    if not V2_PY.exists():
        print(f"ERROR: eddy-v2 venv python not found at {V2_PY}", file=sys.stderr)
        return False
    env = dict(os.environ)
    env["PYTHONPATH"] = str(V2_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    if fake:
        env["EDDY_V2_FAKE_HYPERFRAMES"] = "1"
    proc = subprocess.run(
        [str(V2_PY), "-c", _RUNNER, run_dir, identity, hook,
         "1" if portrait else "0", str(duration), str(out)],
        capture_output=True, text=True, env=env)
    if proc.returncode != 0 or not out.exists():
        print(proc.stderr[-3000:], file=sys.stderr)
        return False
    return True


def probe_wh(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, text=True).stdout.strip()
    try:
        w, h = (int(x) for x in out.split("x")[:2])
        return w, h
    except ValueError:
        return 1920, 1080


def composite(base: Path, overlay: Path, out: Path) -> bool:
    w, h = probe_wh(base)
    fc = (f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
          f"format=rgba,{KEY}[ov];"
          f"[0:v][ov]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]")
    out.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        ["nice", "ffmpeg", "-y", "-i", str(base), "-i", str(overlay), "-filter_complex", fc,
         "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-c:a", "copy", "-movflags", "+faststart", str(out)],
        capture_output=True, text=True)
    if cp.returncode != 0:
        print(cp.stderr[-2500:], file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="HyperFrames motion render (default engine).")
    ap.add_argument("--brief", help="brief.json → custom icon-led layer (preferred)")
    ap.add_argument("--hook", help="text → eddy-v2 text scaffolder (fallback)")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--identity", default="threadify-fc")
    ap.add_argument("--portrait", action="store_true")
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--composite-over")
    ap.add_argument("--composite-out")
    ap.add_argument("--fake", action="store_true", help="GPU-free dry run (ffmpeg testsrc stand-in)")
    args = ap.parse_args()

    if not args.brief and not args.hook:
        print("ERROR: pass --brief brief.json (preferred) or --hook \"text\".", file=sys.stderr)
        return 2

    out = Path(args.out)
    if args.brief:
        brief = json.loads(Path(args.brief).read_text())
        w = int(brief.get("width", 1080 if args.portrait else 1920))
        h = int(brief.get("height", 1920 if args.portrait else 1080))
        brief.setdefault("width", w); brief.setdefault("height", h)
        project = Path(args.run_dir) / ("shorts-card" if args.portrait else "long-overlay")
        dur = scaffold_custom_project(project, brief)
        ok = render_custom_node(project, out, args.fake, w, h, dur)
        mode = "custom_brief"
    else:
        ok = render_hook_scaffolder(args.run_dir, args.identity, args.hook, args.portrait,
                                    args.duration, out, args.fake)
        mode = "hook_scaffolder"

    if not ok:
        print("ERROR: hyperframes motion render failed.", file=sys.stderr)
        return 3

    result = {"event": "motion_rendered", "mode": mode, "overlay": str(out), "fake": args.fake}
    if args.composite_over and args.composite_out:
        if not composite(Path(args.composite_over), out, Path(args.composite_out)):
            print("ERROR: motion composite failed.", file=sys.stderr)
            return 4
        result["composite_out"] = args.composite_out
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
