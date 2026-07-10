#!/usr/bin/env python3
"""Motion render — on-brand HyperFrames motion (the DEFAULT motion engine).

Both modes render through the supported `npx hyperframes` CLI using Eddy's pinned `threadify-fc`
identity projection and composite a keyed-alpha overlay onto a base clip.

  --brief brief.json  (PREFERRED, iconography-forward): build a CUSTOM icon/image-led index.html
      (SVG icons, provider chips, framed real screenshots, stat callouts, flow diagrams — minimal
      supporting text, NO "EDDY V2" watermark) and render it via the node runner directly. This is
      the "custom animated HTML layer" — icon-led, not text-led.
  --hook "text"       (FALLBACK): build a minimal one-beat HyperFrames composition.

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
import shutil
import subprocess
import sys
from pathlib import Path

from eddy.motion_layout import extract_video_frame, resolve_motion_layout

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_DIR = ROOT / "assets" / "motion" / "threadify-fc"
GSAP_SOURCE = ROOT / "assets" / "vendor" / "gsap.min.js"

# Key the black background out to alpha, then overlay.
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
  .ring { position:absolute; right:120px; bottom:96px; width:360px; height:360px; opacity:0.16; z-index:1; }
  .chrome { position:absolute; left:88px; right:88px; top:60px; display:flex; align-items:center;
    justify-content:space-between; font-family:var(--mono); letter-spacing:0.22em; font-weight:700;
    font-size:20px; color:var(--muted,#737373); z-index:8; }
  .chrome .b { display:flex; align-items:center; gap:14px; color:var(--text); }
  .chrome .b img { width:30px; height:30px; }
  .frameline { position:absolute; left:88px; right:88px; top:104px; height:2px; transform-origin:left center;
    background: linear-gradient(90deg, var(--accent,#FF0000), var(--panel-edge,#282626)); z-index:8; }
  .scene { position:absolute; inset:0; opacity:0; z-index:3; pointer-events:none; }
  .contextual-panel { position:absolute; box-sizing:border-box; overflow:hidden; display:flex;
    flex-direction:column; border-radius:20px; border:1px solid rgba(255,255,255,0.38);
    box-shadow:0 24px 60px rgba(0,0,0,0.28),0 2px 10px rgba(0,0,0,0.18); }
  .skin-light { color:#17243b; background:#f4f5f7; border-color:rgba(20,28,45,0.18); }
  .skin-dark { color:#f7f7f8; background:#34363d; border-color:rgba(255,255,255,0.22); }
  .windowbar { height:38px; flex:0 0 38px; display:flex; align-items:center; gap:8px;
    padding:0 16px; box-sizing:border-box; border-bottom:1px solid rgba(127,127,127,0.24);
    background:rgba(127,127,127,0.10); }
  .traffic { width:10px; height:10px; border-radius:50%; box-shadow:inset 0 0 0 1px rgba(0,0,0,0.12); }
  .traffic.red { background:#ff5f57; } .traffic.amber { background:#febc2e; } .traffic.green { background:#28c840; }
  .window-title { margin-left:8px; min-width:0; overflow:hidden; white-space:nowrap; text-overflow:ellipsis;
    font-family:var(--mono); font-size:14px; font-weight:700; letter-spacing:0; opacity:0.72;
    text-transform:uppercase; }
  .panel-body { min-height:0; flex:1; display:flex; flex-direction:column; align-items:center;
    justify-content:center; gap:14px; padding:20px 24px 24px; box-sizing:border-box; text-align:center; }
  .accent-rule { height:3px; width:48px; border-radius:2px; background:var(--accent,#FF0000);
    transform-origin:center; }
  .label { font-family:var(--display); font-weight:800; font-size:30px; line-height:1.06;
    letter-spacing:0; max-width:100%; }
  .row { width:100%; display:flex; align-items:stretch; justify-content:center; gap:12px; flex-wrap:nowrap; }
  .tile { min-width:0; flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;
    gap:10px; padding:14px 12px; border-radius:12px; background:rgba(127,127,127,0.12);
    border:1px solid rgba(127,127,127,0.24); }
  .tile .ic { width:56px; height:56px; }
  .tile .cap { font-family:var(--mono); font-weight:700; font-size:16px; letter-spacing:0;
    text-transform:uppercase; }
  .chip { min-width:0; flex:1; padding:16px 12px; border-radius:12px; font-family:var(--mono);
    font-weight:700; font-size:20px; letter-spacing:0; background:rgba(127,127,127,0.12);
    border:1px solid rgba(127,127,127,0.24); border-left:4px solid var(--accent,#FF0000); }
  .stat { font-family:var(--display); font-weight:900; letter-spacing:0; color:var(--accent,#FF0000);
    line-height:0.94; max-width:100%; white-space:normal; overflow-wrap:anywhere; }
  .sub { font-family:var(--mono); font-weight:700; font-size:18px; letter-spacing:0;
    text-transform:uppercase; }
  .imgwrap { width:100%; min-height:0; overflow:hidden; border-radius:12px;
    border:1px solid rgba(127,127,127,0.24); background:rgba(127,127,127,0.10); padding:8px;
    box-sizing:border-box; }
  .imgwrap img { display:block; width:100%; max-height:170px; object-fit:contain; }
  .flow { width:100%; display:flex; align-items:center; justify-content:center; gap:8px; flex-wrap:nowrap; }
  .node { min-width:0; flex:1; padding:14px 10px; border-radius:12px; font-family:var(--display);
    font-weight:800; font-size:18px; line-height:1.08; background:rgba(127,127,127,0.12);
    border:1px solid rgba(127,127,127,0.24); display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:8px; overflow-wrap:anywhere; }
  .node .ic { width:38px; height:38px; color:var(--accent,#FF0000); display:block; }
  .chip.ico { display:flex; flex-direction:column; align-items:center; gap:8px; }
  .chip .ic { width:38px; height:38px; display:block; }
  .arrow { color:var(--accent,#FF0000); font-family:var(--mono); font-weight:700; font-size:26px; padding:0 2px; }
  #stage.portrait .contextual-panel { border-radius:24px; }
  #stage.portrait .windowbar { height:44px; flex-basis:44px; }
  #stage.portrait .panel-body { padding:20px; gap:12px; }
  #stage.portrait .flow { flex-direction:column; gap:6px; }
  #stage.portrait .flow .arrow { transform:rotate(90deg); line-height:0.7; }
  #stage.portrait .node { width:100%; flex:auto; padding:9px 12px; font-size:17px; flex-direction:row; }
  #stage.portrait .node .ic { width:28px; height:28px; }
  #stage.portrait .label { font-size:28px; }
"""


def _beat_markup(i: int, b: dict, *, portrait: bool) -> str:
    layout = b.get("layout", "icons")
    title = esc(b.get("kicker") or b.get("label") or "Proof")
    rule = '<div class="accent-rule"></div>'
    if layout == "image":
        cap = f'<div class="label">{esc(b["label"])}</div>' if b.get("label") else ""
        inner = f'<div class="imgwrap"><img src="./img-{i}.png" alt=""/></div>{cap}'
    elif layout == "chips":
        parts = []
        for c in b.get("chips", []):
            if isinstance(c, dict):  # icon-led chip: icon over label
                ic = c.get("svg") or c.get("icon") or "check"
                lab = esc(c.get("label") or c.get("text") or "")
                parts.append(f'<div class="chip ico stagger"><span class="ic">{svg(ic)}</span>{lab}</div>')
            else:                    # legacy bare-text chip
                parts.append(f'<div class="chip stagger">{esc(c)}</div>')
        inner = f'<div class="row">{"".join(parts)}</div>'
    elif layout == "icons":
        tiles = "".join(
            f'<div class="tile stagger"><span class="ic">{svg(ic.get("svg","check"))}</span>'
            f'<span class="cap">{esc(ic.get("label",""))}</span></div>'
            for ic in b.get("icons", []))
        inner = f'<div class="row">{tiles}</div>'
    elif layout == "stat":
        sub = f'<div class="sub stagger">{esc(b["label"])}</div>' if b.get("label") else ""
        inner = f'<div class="stat stagger">{esc(b.get("value",""))}</div>{sub}'
    elif layout == "flow":
        parts = []
        for j, n in enumerate(b.get("nodes", [])):
            if j:
                parts.append('<span class="arrow stagger">&#8594;</span>')
            if isinstance(n, dict):  # icon-led node: icon over label
                ic = n.get("svg") or n.get("icon") or "check"
                txt = esc(n.get("text") or n.get("label") or "")
                parts.append(f'<div class="node stagger"><span class="ic">{svg(ic)}</span>{txt}</div>')
            else:                    # legacy bare-text node
                parts.append(f'<div class="node stagger">{esc(n)}</div>')
        inner = f'<div class="flow">{"".join(parts)}</div>'
    else:
        lbl = f'<div class="label">{esc(b.get("label",""))}</div>' if b.get("label") else ""
        inner = lbl
    default = (60, 1325, 454, 461) if portrait else (77, 140, 595, 281)
    x, y = int(b.get("x", default[0])), int(b.get("y", default[1]))
    width, height = int(b.get("w", default[2])), int(b.get("h", default[3]))
    theme = b.get("theme", "dark")
    layout_class = esc(layout.replace("_", "-"))
    return (
        f'<div id="scene-{i}" class="scene"><div class="block contextual-panel '
        f'skin-{esc(theme)} layout-{layout_class}" style="left:{x}px;top:{y}px;width:{width}px;height:{height}px">'
        '<div class="windowbar"><span class="traffic red"></span><span class="traffic amber"></span>'
        f'<span class="traffic green"></span><span class="window-title">{title}</span></div>'
        f'<div class="panel-body">{rule}{inner}</div></div></div>'
    )


def _timeline(beats: list[dict]) -> str:
    lines = ["window.__timelines = window.__timelines || {};",
             "const tl = gsap.timeline({ paused: true });"]
    for i, b in enumerate(beats):
        s = float(b["start"]); d = float(b.get("dur", 4.0))
        lines += [
            f'tl.set("#scene-{i}", {{opacity:1}}, {s:.3f});',
            f'tl.from("#scene-{i} .block", {{y:18, scale:0.98, opacity:0, duration:0.42, ease:"power3.out"}}, {s + 0.04:.3f});',
            f'tl.from("#scene-{i} .accent-rule", {{scaleX:0, duration:0.34, ease:"power3.out"}}, {s + 0.20:.3f});',
            f'tl.from("#scene-{i} .stagger", {{y:10, opacity:0, duration:0.30, stagger:0.07, ease:"power2.out"}}, {s + 0.24:.3f});',
            f'tl.to("#scene-{i} .block", {{y:-8, scale:0.99, opacity:0, duration:0.28, ease:"power2.in"}}, {s + d - 0.28:.3f});',
            f'tl.set("#scene-{i}", {{opacity:0}}, {s + d:.3f});',
        ]
    lines.append('window.__timelines["eddy"] = tl;')
    return "\n".join(lines)


def lint_brief(brief: dict) -> list[str] | None:
    """Iconography enforcement (T2). On the body (mode:cutaway) or when enforce_iconography is set,
    a beat's LEAD must be a visual, not bare text: flow nodes and chips need an icon; a stat's
    supporting line must be a short label, not a sentence. Returns error strings (naming the beat) or
    None. Lighter Shorts label overlays (no enforce flag) are not constrained."""
    if not (brief.get("mode") == "cutaway" or brief.get("enforce_iconography")):
        return None
    errs: list[str] = []
    for i, b in enumerate(brief.get("beats", [])):
        layout = b.get("layout", "icons")
        if layout == "flow":
            for j, n in enumerate(b.get("nodes", [])):
                if not (isinstance(n, dict) and (n.get("svg") or n.get("icon") or n.get("image"))):
                    errs.append(f"beat[{i}] flow node[{j}] is bare text — needs an icon "
                                f"(use {{\"icon\":\"swap\",\"text\":\"...\"}})")
        elif layout == "chips":
            for j, c in enumerate(b.get("chips", [])):
                if not (isinstance(c, dict) and (c.get("svg") or c.get("icon") or c.get("logo"))):
                    errs.append(f"beat[{i}] chip[{j}] is bare text — needs an icon/logo "
                                f"(use {{\"icon\":\"chip\",\"label\":\"...\"}})")
        elif layout == "stat":
            lbl = str(b.get("label", ""))
            if len(lbl.split()) > 5:
                errs.append(f"beat[{i}] stat label is a sentence ({len(lbl.split())} words) — "
                            f"use a short label (≤5 words)")
    return errs or None


def build_custom_html(brief: dict, needle_rel: str | None, ring_rel: str | None,
                      ground: str = "#000") -> str:
    w = int(brief.get("width", 1920)); h = int(brief.get("height", 1080))
    portrait = h > w
    stat_size = 72 if portrait else 88
    beats = brief.get("beats", [])
    dur = float(brief.get("duration") or max((float(b["start"]) + float(b.get("dur", 4.0)) for b in beats), default=6.0))
    # hud = persistent brand chrome + frameline + ring (good on dark motion-dominant hooks). Set
    # "hud":"none" for overlays on a screen demo (body) so only the beat cards show — no top clutter.
    hud = brief.get("hud", "persistent") != "none"
    if hud:
        brand = ('<span class="b">'
                 + (f'<img src="./{needle_rel}" alt=""/>' if needle_rel else "")
                 + 'THREADIFY</span>')
        ring = f'<img class="ring" src="./{ring_rel}" alt="" data-layout-ignore>' if ring_rel else ""
        chrome = f'<div class="chrome">{brand}<span>THREADIFY-FC</span></div><div class="frameline" data-layout-ignore></div>'
    else:
        ring = ""
        chrome = ""
    scenes = "\n".join(_beat_markup(i, b, portrait=portrait) for i, b in enumerate(beats))
    return f"""<!doctype html>
<html><head><meta charset="utf-8" />
<style>{_CSS}
  #stage {{ width:{w}px; height:{h}px; }}
  .stat {{ font-size:{stat_size}px; }}
  /* cutaway = OPAQUE full-frame ground (replaces the screen); overlay path keeps #000 for the key */
  body {{ background:{ground}; }} #stage {{ background:{ground}; }}
</style>
<script src="./gsap.min.js"></script>
</head><body>
<div id="stage" class="{'portrait' if portrait else 'landscape'}" data-composition-id="eddy" data-start="0" data-duration="{dur:.3f}" data-track-index="0" data-width="{w}" data-height="{h}">
  {ring}
  {chrome}
  {scenes}
</div>
<script>
{_timeline(beats)}
</script>
</body></html>
"""


def scaffold_custom_project(project: Path, brief: dict, ground: str = "#000") -> float:
    project.mkdir(parents=True, exist_ok=True)
    # identity assets (frozen — copied, never edited)
    for f in ("identity.css", "font-face.css"):
        src = IDENTITY_DIR / f
        if src.exists():
            shutil.copy2(src, project / f)
        elif f == "font-face.css":
            (project / f).write_text("")  # optional import must resolve
    if not GSAP_SOURCE.exists():
        raise RuntimeError(f"bundled_gsap_missing:{GSAP_SOURCE}")
    shutil.copy2(GSAP_SOURCE, project / "gsap.min.js")
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
    html_doc = build_custom_html(brief, needle_rel, ring_rel, ground)
    (project / "index.html").write_text(html_doc, encoding="utf-8")
    duration = float(brief.get("duration") or max(
        (float(b["start"]) + float(b.get("dur", 4.0)) for b in brief.get("beats", [])), default=6.0))
    (project / "hyperframes.json").write_text(json.dumps({"entry": "index.html"}, indent=2) + "\n")
    (project / "meta.json").write_text(json.dumps({"product": "Eddy", "duration": duration}, indent=2) + "\n")
    (project / "DESIGN.md").write_text(
        "# Eddy Motion Design\n\nPinned threadify-fc identity: quiet navy, gold accent, one visual idea at a time.\n"
    )
    frame = IDENTITY_DIR / "frame.md"
    (project / "frame.md").write_text(frame.read_text() if frame.exists() else "# Eddy Frame\n")
    storyboard = "# Storyboard\n\n" + "\n".join(
        f"- {beat.get('start', 0)}s: {beat.get('kicker') or beat.get('label') or beat.get('layout', 'beat')}"
        for beat in brief.get("beats", [])
    ) + "\n"
    (project / "storyboard.md").write_text(storyboard)
    (project / "storyboard.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Eddy storyboard</title><pre>"
        + html.escape(storyboard)
        + "</pre>\n"
    )
    return duration


def render_custom_node(project: Path, out: Path, fake: bool, w: int, h: int, dur: float) -> bool:
    """Run the HyperFrames lint/validate/inspect contract, then render the composition."""
    if fake:
        subprocess.run(["nice", "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"testsrc2=size={w}x{h}:rate=30:duration={dur}", "-vf",
                        "eq=brightness=-0.25:saturation=0.45", "-an", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(out)], check=False)
        return out.exists()
    checks = []
    for command, receipt in (
        ("lint", "motion-lint.json"),
        ("validate", "motion-validate.json"),
        ("inspect", "motion-inspect.json"),
    ):
        check = subprocess.run(
            ["npx", "hyperframes", command, str(project), "--json"],
            capture_output=True,
            text=True,
        )
        (project / receipt).write_text(check.stdout or check.stderr or "{}")
        checks.append(check.returncode == 0)
    if not all(checks):
        return False
    r = subprocess.run(
        [
            "npx", "hyperframes", "render", str(project), "--quality", "draft",
            "--strict", "--workers", "1", "--output", str(out),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not out.exists():
        print((r.stderr or r.stdout)[-2500:], file=sys.stderr)
        return False
    return True


def render_hook_scaffolder(run_dir: str, identity: str, hook: str, portrait: bool,
                           duration: float, out: Path, fake: bool) -> bool:
    project = Path(run_dir) / "project"
    width, height = ((1080, 1920) if portrait else (1920, 1080))
    brief = {
        "width": width,
        "height": height,
        "duration": duration,
        "beats": [{"start": 0.0, "dur": duration, "layout": "stat", "label": hook}],
    }
    actual_duration = scaffold_custom_project(project, brief)
    return render_custom_node(project, out, fake, width, height, actual_duration)


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


def finalize_cutaway(raw: Path, out: Path, dur: float, fade: float = 0.15) -> bool:
    """Turn the rendered (opaque-ground) motion into a standalone full-frame cutaway SEGMENT:
    short fade in/out, yuv420p, 30fps, VIDEO-ONLY (the body's narration audio plays under it when the
    timeline overlays this clip in place of the screen). No colorkey — it REPLACES the screen."""
    fo = max(0.0, dur - fade)
    vf = (f"fade=t=in:st=0:d={fade:.3f},fade=t=out:st={fo:.3f}:d={fade:.3f},"
          f"setsar=1,fps=30,format=yuv420p")
    out.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        ["nice", "ffmpeg", "-y", "-i", str(raw), "-an", "-vf", vf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", "30",
         "-movflags", "+faststart", str(out)],
        capture_output=True, text=True)
    if cp.returncode != 0:
        print(cp.stderr[-2000:], file=sys.stderr)
        return False
    return True


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
    ap.add_argument("--hook", help="text → minimal one-beat HyperFrames composition (fallback)")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--identity", default="threadify-fc")
    ap.add_argument("--portrait", action="store_true")
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--composite-over")
    ap.add_argument("--composite-out")
    ap.add_argument("--cutaway", action="store_true",
                    help="render an OPAQUE full-frame cutaway segment (body B-roll that REPLACES the "
                         "screen); no colorkey, faded, video-only. Also triggered by brief mode:cutaway")
    ap.add_argument("--fade", type=float, default=0.15, help="cutaway fade in/out, seconds")
    ap.add_argument("--fake", action="store_true", help="GPU-free dry run (ffmpeg testsrc stand-in)")
    args = ap.parse_args()

    if not args.brief and not args.hook:
        print("ERROR: pass --brief brief.json (preferred) or --hook \"text\".", file=sys.stderr)
        return 2

    out = Path(args.out)
    if args.brief:
        brief = json.loads(Path(args.brief).read_text())
        cutaway = args.cutaway or brief.get("mode") == "cutaway"
        if cutaway:
            brief["mode"] = "cutaway"  # so lint_brief enforces iconography on the body
        w = int(brief.get("width", 1080 if args.portrait else 1920))
        h = int(brief.get("height", 1920 if args.portrait else 1080))
        brief.setdefault("width", w); brief.setdefault("height", h)
        placement_proof = None
        if not cutaway:
            frames = []
            base = Path(args.composite_over) if args.composite_over else None
            for beat in brief.get("beats", []):
                frame = (
                    extract_video_frame(
                        base,
                        float(beat.get("start", 0.0)) + float(beat.get("dur", 1.0)) * 0.5,
                        width=w,
                        height=h,
                    )
                    if base is not None and base.exists()
                    else None
                )
                frames.append(frame)
            brief, placement_proof = resolve_motion_layout(
                brief,
                frames,
                portrait=h > w,
            )
        lint_errs = lint_brief(brief)
        if lint_errs:
            print("ERROR: iconography lint failed (body motion must be icon-led, not text):",
                  file=sys.stderr)
            for e in lint_errs:
                print(f"  - {e}", file=sys.stderr)
            return 2
        project = Path(args.run_dir) / ("shorts-card" if args.portrait else "long-overlay")
        # cutaway renders on an OPAQUE ground and becomes a standalone segment; overlay path stays #000
        dur = scaffold_custom_project(project, brief, ground="#0a0a0a" if cutaway else "#000")
        if placement_proof is not None:
            (project / "resolved-brief.json").write_text(json.dumps(brief, indent=2) + "\n")
            (project / "placement-proof.json").write_text(
                json.dumps(placement_proof, indent=2) + "\n"
            )
        if cutaway:
            raw = out.with_suffix(".raw.mp4")
            ok = render_custom_node(project, raw, args.fake, w, h, dur)
            if ok:
                ok = finalize_cutaway(raw, out, dur, args.fade)
                try:
                    raw.unlink()
                except OSError:
                    pass
            mode = "cutaway"
        else:
            ok = render_custom_node(project, out, args.fake, w, h, dur)
            mode = "custom_brief"
    else:
        cutaway = False
        ok = render_hook_scaffolder(args.run_dir, args.identity, args.hook, args.portrait,
                                    args.duration, out, args.fake)
        mode = "hook_scaffolder"

    if not ok:
        print("ERROR: hyperframes motion render failed.", file=sys.stderr)
        return 3

    result = {"event": "motion_rendered", "mode": mode, "overlay": str(out), "fake": args.fake}
    # A cutaway is a standalone opaque segment — never colorkey-composited over a base.
    if not cutaway and args.composite_over and args.composite_out:
        if not composite(Path(args.composite_over), out, Path(args.composite_out)):
            print("ERROR: motion composite failed.", file=sys.stderr)
            return 4
        result["composite_out"] = args.composite_out
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
