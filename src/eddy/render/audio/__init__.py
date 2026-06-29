"""Studio Sound: local audio enhancement (Descript-style) for rendered output.

Chain: [heavy speech enhancement backend if available] -> spectral click/clip repair ->
ffmpeg speech EQ (high-pass + presence lift + FFT denoise) -> two-pass EBU R128 loudnorm
to a YouTube target.

Applied to the RENDERED output's audio full-track (never the source — hard gate), then
remuxed with the untouched video stream. ffmpeg-only is the always-available path; heavy
models are used only when their backend/wrapper is installed and receipt-proven.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from eddy.config import AudioConfig
from eddy.media.ffmpeg import run_ffmpeg

from . import _backends, _candidates, _filters, _measurement, _profiles
from ._backends import (
    _deep_filter,
    _enhancer_status,
    _heavy_enhance,
    _resemble_enhance,
    _which_binary,
)
from ._candidates import (
    _audio_sample_args,
    _candidate_score,
    _echo_gate_pass,
    _loudness_gate_pass,
    _render_profile_candidate,
    _select_best_candidate,
    _strong_cleanup_gate_pass,
)
from ._filters import (
    _available_audio_filters,
    _profile_polish_chain,
    _speech_eq,
    _spectral_repair_chain,
)
from ._measurement import _click_event_count, _echo_artifact_score, measure_lufs
from ._profiles import (
    STUDIO_SOUND_PROFILES,
    StudioSoundProfile,
    _studio_sound_profile_names,
)

__all__ = [
    "STUDIO_SOUND_PROFILES",
    "StudioSoundProfile",
    "studio_sound",
    "measure_lufs",
    "run_ffmpeg",
    "_backends",
    "_candidates",
    "_filters",
    "_measurement",
    "_profiles",
    "_deep_filter",
    "_enhancer_status",
    "_heavy_enhance",
    "_resemble_enhance",
    "_which_binary",
    "_audio_sample_args",
    "_candidate_score",
    "_echo_gate_pass",
    "_loudness_gate_pass",
    "_render_profile_candidate",
    "_select_best_candidate",
    "_strong_cleanup_gate_pass",
    "_available_audio_filters",
    "_profile_polish_chain",
    "_speech_eq",
    "_spectral_repair_chain",
    "_click_event_count",
    "_echo_artifact_score",
    "_studio_sound_profile_names",
]


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

        before_clicks = _click_event_count(raw, cfg.click_threshold)

        # optional heavy speech enhancement model(s), then portable spectral polish
        src, backend, backend_attempts = _heavy_enhance(raw, cfg, run_dir, receipts=receipts)
        if backend == "ffmpeg_only" and cfg.require_heavy_backend:
            result = {
                "applied": False,
                "quality_gate_pass": False,
                "strong_cleanup_gate_pass": False,
                "strong_studio_sound": False,
                "mode": "local_studio_mic",
                "enhancement_backend": backend,
                "backend_attempts": backend_attempts,
                "lufs_before": before,
                "click_events_before": before_clicks,
                "error": "heavy Studio Sound backend required but not available; run `eddy studio-sound install`",
            }
            if receipts is not None:
                receipts.log("studio_sound", **result)
            return result

        candidates = [
            _render_profile_candidate(raw, src, STUDIO_SOUND_PROFILES[name], cfg, work, run_dir, receipts=receipts)
            for name in _studio_sound_profile_names(cfg)
        ]
        selected = _select_best_candidate(candidates, before_clicks, cfg)
        clean = Path(selected["path"])
        after_clicks = int(selected.get("click_events_after") or 0)
        click_gate_pass = bool(selected.get("click_gate_pass"))
        echo_gate_pass = bool(selected.get("echo_gate_pass"))
        selected_loudness_gate_pass = _loudness_gate_pass(selected, cfg)
        strong_cleanup_gate_pass = _strong_cleanup_gate_pass(selected, cfg)
        quality_gate_pass = (
            click_gate_pass
            and echo_gate_pass
            and selected_loudness_gate_pass
            and strong_cleanup_gate_pass
        )
        gate_error = "" if strong_cleanup_gate_pass else (
            "Strong Studio Sound requires a heavy cleanup candidate; source_reference/loudness-only "
            "cannot satisfy the gate."
        )

        samples = {}
        if cfg.write_ab_samples:
            samples_dir = Path(video).parent / "audio-qa-samples"
            samples_dir.mkdir(exist_ok=True)
            raw_sample = samples_dir / "before-studio-sound.wav"
            clean_sample = samples_dir / "after-studio-sound.wav"
            run_ffmpeg(_audio_sample_args(raw, 0.0, 12.0, raw_sample), run_dir=run_dir, receipts=receipts)
            run_ffmpeg(_audio_sample_args(clean, 0.0, 12.0, clean_sample), run_dir=run_dir, receipts=receipts)
            samples = {"before": str(raw_sample), "after": str(clean_sample)}

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
            receipts.log(
                "studio_sound",
                applied=True,
                quality_gate_pass=quality_gate_pass,
                mode="local_studio_mic",
                profile=selected["profile"],
                lufs_before=before,
                lufs_after=after,
                enhancement_backend=backend,
                backend_attempts=backend_attempts,
                click_events_before=before_clicks,
                click_events_after=after_clicks,
                click_gate_pass=click_gate_pass,
                echo_gate_pass=echo_gate_pass,
                loudness_gate_pass=selected_loudness_gate_pass,
                strong_cleanup_gate_pass=strong_cleanup_gate_pass,
                strong_studio_sound=quality_gate_pass,
                echo_artifact_score=selected.get("echo_artifact_score"),
                mouth_click_cleanup=cfg.mouth_click_cleanup,
                filter_chain=selected.get("filter_chain"),
                wet_dry_mix=selected.get("wet_dry_mix"),
                studio_sound_candidates=candidates,
                ab_samples=samples,
                error=gate_error,
                public_reference="Descript-style voice enhancement, denoise/echo reduction, room-tone smoothing at edits",
            )
        return {
            "applied": True,
            "quality_gate_pass": quality_gate_pass,
            "mode": "local_studio_mic",
            "profile": selected["profile"],
            "enhancement_backend": backend,
            "backend_attempts": backend_attempts,
            "lufs_before": before,
            "lufs_after": after,
            "click_events_before": before_clicks,
            "click_events_after": after_clicks,
            "click_gate_pass": click_gate_pass,
            "echo_gate_pass": echo_gate_pass,
            "loudness_gate_pass": selected_loudness_gate_pass,
            "strong_cleanup_gate_pass": strong_cleanup_gate_pass,
            "strong_studio_sound": quality_gate_pass,
            "echo_artifact_score": selected.get("echo_artifact_score"),
            "ab_samples": samples,
            "error": gate_error,
            "mouth_click_cleanup": cfg.mouth_click_cleanup,
            "filter_chain": selected.get("filter_chain"),
            "wet_dry_mix": selected.get("wet_dry_mix"),
            "studio_sound_candidates": candidates,
        }
    except Exception as e:
        if receipts is not None:
            receipts.log("studio_sound", applied=False, error=str(e)[:300])
        return {
            "applied": False,
            "quality_gate_pass": False,
            "strong_cleanup_gate_pass": False,
            "strong_studio_sound": False,
            "error": str(e)[:300],
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
