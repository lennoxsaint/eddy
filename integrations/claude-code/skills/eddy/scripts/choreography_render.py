#!/usr/bin/env python3
"""Render an Eddy v3.2 full-frame scene timeline through HyperFrames."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from eddy.choreography import build_hyperframes_project


ROOT = Path(__file__).resolve().parents[1]


def _render(project: Path, output: Path, *, fake: bool, width: int, height: int, duration: float) -> bool:
    raw = output.with_suffix(".visual.mp4")
    if fake:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                f"testsrc2=size={width}x{height}:rate=30:duration={duration}",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw),
            ],
            check=False,
        )
        return result.returncode == 0 and raw.exists()
    for command, receipt in (
        ("lint", "hyperframes-lint.json"),
        ("validate", "hyperframes-validate.json"),
        ("inspect", "hyperframes-inspect.json"),
    ):
        command_args = ["npx", "hyperframes", command, str(project)]
        if command == "inspect":
            command_args.append("--strict")
        command_args.append("--json")
        result = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            check=False,
        )
        (project / receipt).write_text(result.stdout or result.stderr or "{}")
        if result.returncode != 0:
            return False
    snapshots = subprocess.run(
        ["npx", "hyperframes", "snapshot", str(project), "--frames", "5"],
        capture_output=True,
        text=True,
        check=False,
    )
    (project / "hyperframes-snapshot.json").write_text(
        json.dumps(
            {
                "event": "hyperframes_snapshot",
                "returncode": snapshots.returncode,
                "stdout_tail": snapshots.stdout[-1200:],
                "stderr_tail": snapshots.stderr[-1200:],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if snapshots.returncode != 0 or len(list((project / "snapshots").glob("*.png"))) < 5:
        return False
    result = subprocess.run(
        [
            "npx", "hyperframes", "render", str(project), "--quality", "draft",
            "--strict", "--workers", "1", "--output", str(raw),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    (project / "hyperframes-render.json").write_text(
        json.dumps(
            {
                "event": "hyperframes_render",
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
                "stderr_tail": result.stderr[-1200:],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if result.returncode != 0:
        print((result.stderr or result.stdout)[-2500:], file=sys.stderr)
    return result.returncode == 0 and raw.exists()


def _mux_audio(visual: Path, audio: Path, output: Path) -> bool:
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(visual), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output),
        ],
        check=False,
    )
    return result.returncode == 0 and output.exists()


def _media_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render full-frame Eddy visual choreography")
    parser.add_argument("--brief", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fake", action="store_true")
    args = parser.parse_args(argv)

    brief = json.loads(Path(args.brief).read_text())
    project = Path(args.run_dir) / "project"
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_path = Path(brief["frame"])
    design_path = Path(brief.get("design", brief["frame"]))
    actual_frame_sha256 = hashlib.sha256(frame_path.read_bytes()).hexdigest()
    if actual_frame_sha256 != str(brief["frame_sha256"]):
        print("frame_contract_hash_mismatch", file=sys.stderr)
        return 2
    actual_design_sha256 = hashlib.sha256(design_path.read_bytes()).hexdigest()
    expected_design_sha256 = str(brief.get("design_sha256", actual_design_sha256))
    if actual_design_sha256 != expected_design_sha256:
        print("design_contract_hash_mismatch", file=sys.stderr)
        return 2
    audio_source = Path(brief.get("audio_source", brief["camera"]))
    manifest = build_hyperframes_project(
        project,
        scenes=brief["scenes"],
        camera=Path(brief["camera"]),
        screen=Path(brief["screen"]) if brief.get("screen") else None,
        design_markdown=design_path.read_text(),
        design_sha256=expected_design_sha256,
        frame_markdown=frame_path.read_text(),
        frame_sha256=str(brief["frame_sha256"]),
        width=int(brief["width"]),
        height=int(brief["height"]),
        gsap_source=ROOT / "assets" / "vendor" / "gsap.min.js",
        source_roots=tuple(Path(value) for value in brief.get("source_roots", [])),
        duration_override=_media_duration(audio_source),
    )
    duration = float(manifest["duration"])
    if not _render(
        project,
        output,
        fake=args.fake,
        width=int(brief["width"]),
        height=int(brief["height"]),
        duration=duration,
    ):
        return 3
    raw = output.with_suffix(".visual.mp4")
    if not _mux_audio(raw, audio_source, output):
        return 4
    raw.unlink(missing_ok=True)
    provenance = {
        "schema_version": "eddy-visual-provenance-v1",
        "frame_sha256": brief["frame_sha256"],
        "design_sha256": expected_design_sha256,
        "camera_sha256": manifest["camera_sha256"],
        "screen_sha256": manifest["screen_sha256"],
        "asset_sha256": manifest["asset_sha256"],
        "source_authorities": sorted({scene["evidence_authority"] for scene in brief["scenes"]}),
    }
    (project / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    (project / "render-receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "eddy-choreography-render-receipt-v1",
                "visual_render": "pass",
                "audio_mux": "pass",
                "duration": duration,
                "fake": args.fake,
                "output": str(output),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(json.dumps({"event": "visual_choreography_rendered", "output": str(output), "fake": args.fake}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
