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
  .scene.reg-lower { align-items:flex-end; }
  /* opaque band covering the Shorts screen panel. Charcoal (NOT near-black) so the black-key that
     makes the rest transparent doesn't erase it — #444444 sits well above the colorkey threshold. */
  .scene.reg-lower .block { background:#444444; width:100%; box-sizing:border-box;
    min-height:700px; justify-content:center; padding:70px 70px 190px; }
  .scene.reg-upper { align-items:flex-start; }
  .scene.reg-upper .block { background:#444444; width:100%; box-sizing:border-box;
    min-height:640px; justify-content:center; padding:180px 70px 70px; }
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
    border-bottom:6px solid var(--accent,#FF0000); max-width:360px; display:flex; flex-direction:column;
    align-items:center; gap:16px; }
  .node .ic { width:88px; height:88px; color:var(--accent,#FF0000); display:block; }
  .chip.ico { display:flex; flex-direction:column; align-items:center; gap:14px; }
  .chip .ic { width:72px; height:72px; color:var(--text); display:block; }
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
        sub = f'<div class="sub">{esc(b["label"])}</div>' if b.get("label") else ""
        inner = f'<div class="stat">{esc(b.get("value",""))}</div>{sub}'
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
    region = b.get("region", "center")  # center | lower | upper (place clear of face/captions on Shorts)
    return (f'<div id="scene-{i}" class="scene reg-{region}"><div class="block">'
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
    stat_size = 160 if h > w else 300
    stat_width = max(320, w - 140)
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
    scenes = "\n".join(_beat_markup(i, b) for i, b in enumerate(beats))
    return f"""<!doctype html>
<html><head><meta charset="utf-8" />
<style>{_CSS}
  #stage {{ width:{w}px; height:{h}px; }}
  .stat {{ font-size:{stat_size}px; max-width:{stat_width}px; white-space:nowrap; }}
  /* cutaway = OPAQUE full-frame ground (replaces the screen); overlay path keeps #000 for the key */
  body {{ background:{ground}; }} #stage {{ background:{ground}; }}
</style>
<script src="./gsap.min.js"></script>
</head><body>
<div id="stage" data-composition-id="eddy" data-start="0" data-duration="{dur:.3f}" data-track-index="0" data-width="{w}" data-height="{h}">
  <div class="grain" data-layout-ignore></div>
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
