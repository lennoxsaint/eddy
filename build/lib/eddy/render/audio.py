"""Studio Sound: local audio enhancement (Descript-style) for rendered output.

Chain: [DeepFilterNet denoise/dereverb if available] -> ffmpeg speech EQ (high-pass +
presence lift + FFT denoise) -> two-pass EBU R128 loudnorm to a YouTube target.

Applied to the RENDERED output's audio full-track (never the source — hard gate), then
remuxed with the untouched video stream. ffmpeg-only is the always-available path; the
DeepFilterNet pass is a bonus when the binary is installed.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from eddy.config import AudioConfig
from eddy.media.ffmpeg import FFMPEG, run_ffmpeg, run_ffprobe


def _speech_eq(cfg: AudioConfig) -> str:
    return (
        f"highpass=f={cfg.highpass_hz},"
        "afftdn=nf=-25,"
        f"equalizer=f={cfg.presence_hz}:t=q:w=2:g={cfg.presence_gain_db},"
        "alimiter=limit=0.95"
    )


def measure_lufs(media: Path) -> float | None:
    """Integrated loudness (LUFS) via loudnorm measurement pass. None on failure."""
    import subprocess

    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(media),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800,
    )
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.DOTALL)
    if not m:
        return None
    try:
        return float(json.loads(m.group(0))["input_i"])
    except (ValueError, KeyError):
        return None


def _deep_filter(in_wav: Path, out_wav: Path, cfg: AudioConfig, run_dir: Path, receipts=None) -> bool:
    """Run DeepFilterNet if its CLI is installed. Returns True if it produced output."""
    binary = shutil.which(cfg.deep_filter_binary)
    if not binary:
        return False
    import subprocess

    # deep-filter writes <stem>_DeepFilterNet3.wav into the output dir
    proc = subprocess.run(
        [binary, str(in_wav), "-o", str(out_wav.parent)],
        capture_output=True, text=True, timeout=3600,
    )
    if receipts is not None:
        receipts.log("deep_filter", exit_code=proc.returncode)
    if proc.returncode != 0:
        return False
    produced = next(out_wav.parent.glob(f"{in_wav.stem}*DeepFilter*.wav"), None)
    if produced and produced != out_wav:
        produced.rename(out_wav)
    return out_wav.exists()


def studio_sound(video: Path, run_dir: Path, cfg: AudioConfig, receipts=None) -> dict:
    """Enhance the audio of `video` in place. Returns measurements + status.

    Robust + non-fatal: any failure leaves the original video untouched and is logged.
    """
    work = Path(video).parent / "_audio"
    work.mkdir(exist_ok=True)
    before = measure_lufs(video)
    try:
        raw = work / "raw.wav"
        run_ffmpeg(["-i", str(video), "-vn", "-ac", "2", "-ar", "48000", str(raw)], run_dir=run_dir, receipts=receipts)

        # optional DeepFilterNet denoise/dereverb
        dfn = work / "dfn.wav"
        src = dfn if _deep_filter(raw, dfn, cfg, run_dir, receipts) else raw

        # pass 1: measure loudnorm stats after the speech-EQ chain
        import subprocess

        eq = _speech_eq(cfg)
        ln = f"loudnorm=I={cfg.target_lufs}:TP={cfg.true_peak_db}:LRA={cfg.lra}"
        p1 = subprocess.run(
            [FFMPEG, "-hide_banner", "-i", str(src), "-af", f"{eq},{ln}:print_format=json", "-f", "null", "-"],
            capture_output=True, text=True, timeout=1800,
        )
        m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p1.stderr, re.DOTALL)
        meas = json.loads(m.group(0)) if m else {}

        # pass 2: apply EQ + measured (linear) loudnorm -> clean wav
        clean = work / "clean.wav"
        ln2 = ln
        if meas:
            ln2 = (
                f"loudnorm=I={cfg.target_lufs}:TP={cfg.true_peak_db}:LRA={cfg.lra}"
                f":measured_I={meas['input_i']}:measured_TP={meas['input_tp']}"
                f":measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}"
                f":offset={meas.get('target_offset', 0)}:linear=true"
            )
        run_ffmpeg(["-i", str(src), "-af", f"{eq},{ln2}", "-ar", "48000", str(clean)], run_dir=run_dir, receipts=receipts)

        # remux cleaned audio over the untouched video. -shortest bounds the output to the
        # video stream: the loudnorm/EQ filter chain emits ~1s of trailing tail past the video
        # length, which would otherwise overrun the container and trip the av_drift gate. The
        # source audio came from the video, so the trimmed tail carries no speech.
        out = work / "out.mp4"
        run_ffmpeg(
            ["-i", str(video), "-i", str(clean), "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
             "-movflags", "+faststart", str(out)],
            run_dir=run_dir, receipts=receipts,
        )
        out.replace(video)
        after = measure_lufs(video)
        if receipts is not None:
            receipts.log("studio_sound", applied=True, lufs_before=before, lufs_after=after, deep_filter=(src == dfn))
        return {"applied": True, "lufs_before": before, "lufs_after": after}
    except Exception as e:
        if receipts is not None:
            receipts.log("studio_sound", applied=False, error=str(e)[:300])
        return {"applied": False, "error": str(e)[:300]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
