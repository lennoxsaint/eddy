"""Studio Sound: local audio enhancement (Descript-style) for rendered output.

Chain: [heavy speech enhancement backend if available] -> spectral click/clip repair ->
ffmpeg speech EQ (high-pass + presence lift + FFT denoise) -> two-pass EBU R128 loudnorm
to a YouTube target.

Applied to the RENDERED output's audio full-track (never the source — hard gate), then
remuxed with the untouched video stream. ffmpeg-only is the always-available path; heavy
models are used only when their backend/wrapper is installed and receipt-proven.
"""

from __future__ import annotations

import json
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
from ._measurement import _click_event_count, _echo_artifact_score, _mouth_click_hotspot, _mouth_click_score, measure_lufs
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
    "_mouth_click_hotspot",
    "_mouth_click_score",
    "_echo_artifact_score",
    "_studio_sound_profile_names",
]


def _write_audition_matrix(
    raw: Path,
    clean: Path,
    samples_dir: Path,
    run_dir: Path,
    selected: dict,
    candidates: list[dict],
    cfg: AudioConfig,
    receipts=None,
) -> dict:
    samples_dir.mkdir(parents=True, exist_ok=True)
    hotspot = _mouth_click_hotspot(raw)
    windows = [
        {"id": "hook", "start_s": 0.0, "duration_s": 12.0, "reason": "Opening hook A/B sample."},
        {
            "id": "worst_click",
            "start_s": float(hotspot.get("start_s", 0.0) or 0.0),
            "duration_s": float(hotspot.get("duration_s", 12.0) or 12.0),
            "reason": "Densest local mouth-click/transient window.",
            "hotspot": hotspot,
        },
    ]
    for window in windows:
        before = samples_dir / f"before-{window['id']}.wav"
        after = samples_dir / f"after-{window['id']}.wav"
        window_start = float(str(window.get("start_s", 0.0)))
        window_duration = float(str(window.get("duration_s", 12.0)))
        run_ffmpeg(
            _audio_sample_args(raw, window_start, window_duration, before),
            run_dir=run_dir,
            receipts=receipts,
        )
        run_ffmpeg(
            _audio_sample_args(clean, window_start, window_duration, after),
            run_dir=run_dir,
            receipts=receipts,
        )
        window["before_sample"] = str(before)
        window["after_sample"] = str(after)
        before_score = _mouth_click_score(before, max_seconds=window_duration)
        after_score = _mouth_click_score(after, max_seconds=window_duration)
        window["before_mouth_click_score"] = before_score
        window["after_mouth_click_score"] = after_score
        window["after_mouth_click_gate_pass"] = after_score <= cfg.mouth_click_score_max
    matrix = {
        "status": "pass" if all(w["after_mouth_click_gate_pass"] for w in windows) else "blocked",
        "selected_profile": selected.get("profile"),
        "selected_path": selected.get("path"),
        "windows": windows,
        "candidate_rows": [
            {
                "profile": candidate.get("profile"),
                "source_mode": candidate.get("source_mode"),
                "wet_dry_mix": candidate.get("wet_dry_mix"),
                "selection_score": candidate.get("selection_score"),
                "click_gate_pass": candidate.get("click_gate_pass"),
                "mouth_click_gate_pass": candidate.get("mouth_click_gate_pass"),
                "echo_gate_pass": candidate.get("echo_gate_pass"),
                "loudness_gate_pass": candidate.get("loudness_gate_pass", _loudness_gate_pass(candidate, cfg)),
                "strong_cleanup_gate_pass": _strong_cleanup_gate_pass(candidate, cfg),
            }
            for candidate in candidates
        ],
        "policy": (
            "source_reference is A/B reference only; passing default Studio Sound requires local "
            "cleanup that applies real processing and clears click/echo/loudness gates."
        ),
    }
    matrix_path = samples_dir / "studio-sound-audition-matrix.json"
    matrix_path.write_text(json.dumps(matrix, indent=2))
    matrix["path"] = str(matrix_path)
    return matrix


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
        before_mouth_score = _mouth_click_score(raw)

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
                "mouth_click_score_before": before_mouth_score,
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
        mouth_click_gate_pass = bool(selected.get("mouth_click_gate_pass", True))
        echo_gate_pass = bool(selected.get("echo_gate_pass"))
        selected_loudness_gate_pass = _loudness_gate_pass(selected, cfg)
        strong_cleanup_gate_pass = _strong_cleanup_gate_pass(selected, cfg)
        quality_gate_pass = (
            click_gate_pass
            and mouth_click_gate_pass
            and echo_gate_pass
            and selected_loudness_gate_pass
            and strong_cleanup_gate_pass
        )
        gate_error = "" if strong_cleanup_gate_pass else (
            "Strong Studio Sound requires a local cleanup candidate with real processing; "
            "source_reference/loudness-only cannot satisfy the gate."
        )

        samples = {}
        audition_matrix = {}
        if cfg.write_ab_samples:
            samples_dir = Path(video).parent / "audio-qa-samples"
            samples_dir.mkdir(exist_ok=True)
            raw_sample = samples_dir / "before-studio-sound.wav"
            clean_sample = samples_dir / "after-studio-sound.wav"
            run_ffmpeg(_audio_sample_args(raw, 0.0, 12.0, raw_sample), run_dir=run_dir, receipts=receipts)
            run_ffmpeg(_audio_sample_args(clean, 0.0, 12.0, clean_sample), run_dir=run_dir, receipts=receipts)
            samples = {"before": str(raw_sample), "after": str(clean_sample)}
            audition_matrix = _write_audition_matrix(raw, clean, samples_dir, run_dir, selected, candidates, cfg, receipts=receipts)
            if audition_matrix.get("status") != "pass":
                quality_gate_pass = False
                gate_error = "Local Studio Sound audition matrix failed hook/worst-click sample gates."

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
                mouth_click_score_before=before_mouth_score,
                mouth_click_score_after=selected.get("mouth_click_score_after"),
                mouth_click_gate_pass=mouth_click_gate_pass,
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
                audition_matrix=audition_matrix,
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
            "mouth_click_score_before": before_mouth_score,
            "mouth_click_score_after": selected.get("mouth_click_score_after"),
            "mouth_click_gate_pass": mouth_click_gate_pass,
            "echo_gate_pass": echo_gate_pass,
            "loudness_gate_pass": selected_loudness_gate_pass,
            "strong_cleanup_gate_pass": strong_cleanup_gate_pass,
            "strong_studio_sound": quality_gate_pass,
            "echo_artifact_score": selected.get("echo_artifact_score"),
            "ab_samples": samples,
            "audition_matrix": audition_matrix,
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
