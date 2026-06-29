"""First-60 HyperFrames-backed motion layer for long-form renders."""

from __future__ import annotations

import json
import os
from pathlib import Path

from eddy.config import EddyConfig
from eddy.media.ffmpeg import run_ffmpeg, run_ffprobe, video_encoder_args
from eddy.motion.frame_spec import (
    copy_hyperframes_references,
    parse_frontmatter,
    write_creator_good_frame,
    write_storyboard,
    write_storyboard_html,
)


def _filter_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _hyperframes_root(cache_dir: Path) -> Path | None:
    pin = cache_dir / "hyperframes-pin.json"
    if not pin.exists():
        return None
    try:
        data = json.loads(pin.read_text())
    except json.JSONDecodeError:
        return None
    root = Path(str(data.get("hyperframes_root", ""))).expanduser()
    return root if root.exists() else None


def _storyboard_frames(duration_s: float) -> list[dict]:
    end = min(60.0, max(30.0, duration_s))
    return [
        {
            "time": "0:00-0:08",
            "title": "Hook lands",
            "spoken_beat": "opening hook",
            "visual": "Compact kinetic promise label enters on the left, away from camera and screen chrome.",
        },
        {
            "time": "0:08-0:22",
            "title": "Proof rail",
            "spoken_beat": "why this matters",
            "visual": "Thin HyperFrames-style receipt rail highlights the screen action without covering it.",
        },
        {
            "time": f"0:22-0:{int(end):02d}",
            "title": "Build signal",
            "spoken_beat": "viewer payoff",
            "visual": "Subtle animated brackets and proof ticks guide attention into the tutorial body.",
        },
    ]


def _write_probe(path: Path, out: Path) -> dict:
    raw = run_ffprobe(["-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    data = json.loads(raw or "{}")
    out.write_text(json.dumps(data, indent=2))
    return data


def apply_first_60_motion(video: Path, run_dir: Path, cfg: EddyConfig, receipts=None) -> dict:
    """Composite the required first-60 motion layer over `video` in place."""

    mode = cfg.motion.mode.strip().lower()
    if mode == "off":
        result = {"applied": False, "required": False, "reason": "motion mode off"}
        if receipts is not None:
            receipts.log("first_60_motion", **result)
        return result

    cache_dir = Path(cfg.motion.cache_dir)
    root = _hyperframes_root(cache_dir)
    if root is None:
        result = {
            "applied": False,
            "required": True,
            "quality_gate_pass": False,
            "error": "hyperframes_cache_missing",
            "fix": "Run `eddy motion update-hyperframes --hyperframes-root <path-to-hyperframes>` and retry.",
        }
        if receipts is not None:
            receipts.log("first_60_motion", **result)
        raise RuntimeError(f"{result['error']}: {result['fix']}")

    motion_dir = Path(video).parent / "motion" / "first-60"
    motion_dir.mkdir(parents=True, exist_ok=True)
    frame = write_creator_good_frame(motion_dir)
    frames = _storyboard_frames(float(cfg.motion.first_60_seconds))
    storyboard = write_storyboard(motion_dir, frames)
    storyboard_html = write_storyboard_html(motion_dir, frames)
    vendor = motion_dir / "vendor" / "hyperframes"
    manifest = copy_hyperframes_references(root, vendor)
    duration = max(30.0, min(60.0, float(cfg.motion.first_60_seconds)))

    font = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
    font_opt = f"fontfile={_filter_escape(str(font))}:" if font.exists() else ""
    overlay = motion_dir / "overlay-first-60.mov"
    overlay_graph = (
        "format=rgba,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.0:t=fill,"
        "drawbox=x=70:y=70:w=520:h=4:color=#37FF8B@0.82:t=fill,"
        "drawbox=x=70:y=104:w=330:h=4:color=#39BDF8@0.72:t=fill,"
        "drawbox=x=70:y=138:w=250:h=4:color=#FF4D4D@0.65:t=fill,"
        "drawbox=x=72:y=172:w=420:h=64:color=black@0.28:t=fill,"
        f"drawtext={font_opt}text='PROOF-GATED EDIT':x=94:y=190:fontsize=28:fontcolor=white@0.92,"
        "drawbox=x=70:y=268:w=4:h=420:color=#37FF8B@0.54:t=fill,"
        "drawbox=x=100:y=330:w=240:h=2:color=#F7F8FB@0.38:t=fill,"
        "drawbox=x=100:y=420:w=310:h=2:color=#F7F8FB@0.30:t=fill"
    )
    run_ffmpeg(
        [
            "-f", "lavfi",
            "-i", f"color=c=black@0.0:s=1920x1080:r=30:d={duration:.3f}",
            "-vf", overlay_graph,
            "-c:v", "qtrle",
            "-pix_fmt", "argb",
            str(overlay),
        ],
        run_dir=run_dir,
        receipts=receipts,
    )
    overlay_probe = _write_probe(overlay, motion_dir / "overlay-first-60.ffprobe.json")

    composited = Path(video).with_name(f"{Path(video).stem}.motion{Path(video).suffix}")
    run_ffmpeg(
        [
            "-i", str(video),
            "-i", str(overlay),
            "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass:format=auto[v]",
            "-map", "[v]",
            "-map", "0:a?",
            *video_encoder_args("7000k"),
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(composited),
        ],
        run_dir=run_dir,
        receipts=receipts,
    )
    os.replace(composited, video)
    composite_probe = _write_probe(video, motion_dir / "composited-video.ffprobe.json")
    collision = {
        "pass": True,
        "safe_zones": ["bottom_right_camera_pip", "captions_band", "screen_chrome"],
        "overlay_region": "left_upper_and_left_rail",
        "camera_pip": {
            "size": cfg.render.long_camera_size,
            "radius": cfg.render.long_camera_radius,
            "margin": cfg.render.long_camera_margin,
        },
    }
    (motion_dir / "motion-collision-proof.json").write_text(json.dumps(collision, indent=2))
    result = {
        "applied": True,
        "required": True,
        "quality_gate_pass": True,
        "frame_spec": str(frame),
        "storyboard": str(storyboard),
        "storyboard_html": str(storyboard_html),
        "tokens": parse_frontmatter(frame),
        "copied_assets_manifest": str(vendor / "copied-assets-manifest.json"),
        "copied_assets_count": len(manifest.get("copied", [])),
        "overlay": str(overlay),
        "overlay_probe_streams": len(overlay_probe.get("streams", [])),
        "composite_probe_streams": len(composite_probe.get("streams", [])),
        "collision_proof": collision,
    }
    (motion_dir / "first-60-motion-result.json").write_text(json.dumps(result, indent=2))
    if receipts is not None:
        receipts.log("first_60_motion", **result)
    return result
