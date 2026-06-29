"""Candidate rendering, scoring, and selection for Studio Sound."""

from __future__ import annotations

from pathlib import Path

from eddy.config import AudioConfig
from eddy.media.ffmpeg import run_ffmpeg

from ._filters import _profile_polish_chain
from ._measurement import _click_event_count, _echo_artifact_score, measure_lufs
from ._profiles import StudioSoundProfile


def _render_profile_candidate(
    raw: Path,
    enhanced: Path,
    profile: StudioSoundProfile,
    cfg: AudioConfig,
    work: Path,
    run_dir: Path,
    receipts=None,
) -> dict:
    out = work / f"candidate-{profile.name}.wav"
    if profile.source_mode == "reference":
        ln = f"loudnorm=I={cfg.target_lufs}:TP={cfg.true_peak_db}:LRA={cfg.lra}"
        run_ffmpeg(
            ["-i", str(raw), "-af", ln, "-ar", "48000", str(out)],
            run_dir=run_dir,
            receipts=receipts,
        )
        clicks = _click_event_count(out, cfg.click_threshold)
        echo_score = _echo_artifact_score(out)
        return {
            "profile": profile.name,
            "path": str(out),
            "filter_chain": ln,
            "wet_dry_mix": {"dry": 1.0, "wet": 0.0},
            "source_mode": profile.source_mode,
            "notes": profile.notes,
            "lufs_after": measure_lufs(out),
            "reference_echo_artifact_score": echo_score,
            "click_events_after": clicks,
            "click_gate_pass": True,
            "echo_artifact_score": echo_score,
            "echo_gate_pass": True,
        }
    dry = max(0.0, min(0.65, profile.dry_mix))
    if profile.source_mode == "raw":
        dry = max(dry, 0.35)
    wet = 1.0 - dry
    wet_input = raw if profile.source_mode == "raw" else enhanced
    chain = _profile_polish_chain(profile, cfg)
    ln = f"loudnorm=I={cfg.target_lufs}:TP={cfg.true_peak_db}:LRA={cfg.lra}"
    filter_complex = (
        f"[1:a]{chain}[wet0];"
        f"[0:a]volume={dry:.3f}[dry];"
        f"[wet0]volume={wet:.3f}[wet];"
        f"[dry][wet]amix=inputs=2:normalize=0,{ln}[a]"
    )
    run_ffmpeg(
        ["-i", str(raw), "-i", str(wet_input), "-filter_complex", filter_complex, "-map", "[a]", "-ar", "48000", str(out)],
        run_dir=run_dir,
        receipts=receipts,
    )
    before_clicks = _click_event_count(raw, cfg.click_threshold)
    clicks = _click_event_count(out, cfg.click_threshold)
    click_gate_pass = clicks <= before_clicks or clicks <= max(8, int(before_clicks * 0.35))
    reference_echo_score = _echo_artifact_score(raw)
    echo_score = _echo_artifact_score(out)
    echo_gate_pass = _echo_gate_pass(echo_score, reference_echo_score, cfg)
    return {
        "profile": profile.name,
        "path": str(out),
        "filter_chain": chain,
        "wet_dry_mix": {"dry": dry, "wet": wet},
        "source_mode": profile.source_mode,
        "notes": profile.notes,
        "lufs_after": measure_lufs(out),
        "reference_echo_artifact_score": reference_echo_score,
        "click_events_after": clicks,
        "click_gate_pass": click_gate_pass,
        "echo_artifact_score": echo_score,
        "echo_gate_pass": echo_gate_pass,
    }


def _candidate_score(candidate: dict, before_clicks: int, cfg: AudioConfig) -> float:
    clicks = float(candidate.get("click_events_after") or 0)
    click_ratio = clicks / max(1.0, float(before_clicks))
    echo_score = float(candidate.get("echo_artifact_score") or 0.0)
    lufs = candidate.get("lufs_after")
    lufs_penalty = abs(float(lufs) - cfg.target_lufs) / 10.0 if lufs is not None else 0.5
    overprocess_penalty = {
        "source_reference": -0.04,
        "warm_room_tame": 0.00,
        "warm_deep_tame": 0.01,
        "warm_click_tame": 0.02,
        "warm_model_10": 0.05,
        "natural_voice": 0.00,
        "click_rescue": 0.04,
        "broadcast_clean": 0.12,
    }.get(str(candidate.get("profile")), 0.08)
    if candidate.get("click_gate_pass"):
        # Once the click gate passes, do not keep chasing a numerically smaller click count at the
        # cost of a more processed voice. This is the exact dogfood failure: clicks gone, but the
        # audio starts sounding hollow/echoey. A failing click gate still receives the full penalty.
        click_component = min(click_ratio, 1.0) * 0.08
    else:
        click_component = click_ratio * 0.50
    return round(click_component + (echo_score * 0.35) + lufs_penalty + overprocess_penalty, 5)


def _loudness_gate_pass(candidate: dict, cfg: AudioConfig, tolerance: float = 2.0) -> bool:
    """Candidate-level loudness gate.

    Studio Sound can choose a do-not-harm reference candidate, but it still has to be usable in a
    rendered video. A source-preserving pass at -23 LUFS is not a passing Studio Sound result for
    YouTube Shorts, even if click/echo gates pass.
    """
    raw_lufs = candidate.get("lufs_after")
    if raw_lufs is None:
        return False
    try:
        lufs = float(raw_lufs)
    except (TypeError, ValueError):
        return False
    return abs(lufs - float(cfg.target_lufs)) <= tolerance


def _echo_gate_pass(echo_score: float, reference_echo_score: float, cfg: AudioConfig) -> bool:
    """Block material echo regressions without making already-echoey source impossible.

    The absolute floor catches obviously hollow/echoey processing on clean source audio. When the
    source itself scores above that floor, the honest gate is source-relative: a heavy cleanup
    candidate can pass only if it is effectively no worse than the source measurement.
    """
    if not cfg.require_echo_artifact_gate:
        return True
    if reference_echo_score <= cfg.echo_artifact_max_score:
        return echo_score <= cfg.echo_artifact_max_score and echo_score <= reference_echo_score + 0.015
    return echo_score <= reference_echo_score + 0.006


def _strong_cleanup_gate_pass(candidate: dict, cfg: AudioConfig) -> bool:
    """A passing Strong Studio Sound result must include real heavy/wet cleanup.

    `source_reference` is still useful as a do-no-harm comparison or an explicitly lowered policy,
    but it cannot satisfy the default product promise: actual studio-quality voice cleanup.
    """
    if not cfg.require_heavy_backend:
        return True
    profile = str(candidate.get("profile", ""))
    source_mode = str(candidate.get("source_mode", ""))
    if profile == "source_reference" or source_mode == "reference":
        return False
    wet = candidate.get("wet_dry_mix", {}).get("wet", 0.0)
    try:
        wet_amount = float(wet)
    except (TypeError, ValueError):
        wet_amount = 0.0
    return source_mode == "heavy" and wet_amount > 0.0


def _select_best_candidate(candidates: list[dict], before_clicks: int, cfg: AudioConfig) -> dict:
    scored = []
    for candidate in candidates:
        c = dict(candidate)
        c["selection_score"] = _candidate_score(c, before_clicks, cfg)
        c["loudness_gate_pass"] = _loudness_gate_pass(c, cfg)
        scored.append(c)
    passing = [
        c for c in scored
        if c.get("click_gate_pass") and c.get("echo_gate_pass") and c.get("loudness_gate_pass")
    ]
    strong_passing = [c for c in passing if _strong_cleanup_gate_pass(c, cfg)]
    if cfg.require_heavy_backend and strong_passing:
        return min(strong_passing, key=lambda c: c["selection_score"])
    if cfg.require_heavy_backend:
        heavy_pool = [
            c for c in scored
            if c.get("profile") != "source_reference" and c.get("source_mode") == "heavy"
        ]
        if heavy_pool:
            heavy_gate_passes = [
                c for c in heavy_pool
                if c.get("click_gate_pass") and c.get("echo_gate_pass") and c.get("loudness_gate_pass")
            ]
            return min(heavy_gate_passes or heavy_pool, key=lambda c: c["selection_score"])
    reference = next((c for c in passing if c.get("profile") == "source_reference"), None)
    if reference:
        ref_echo = float(reference.get("echo_artifact_score") or 0.0)
        ref_clicks = float(reference.get("click_events_after") or before_clicks or 0)
        materially_better = []
        for c in passing:
            if c.get("profile") == "source_reference":
                continue
            clicks = float(c.get("click_events_after") or 0)
            echo = float(c.get("echo_artifact_score") or 0.0)
            click_reduction = ref_clicks > 12 and clicks <= max(8.0, ref_clicks * 0.65) and echo <= ref_echo + 0.015
            echo_reduction = echo <= ref_echo - 0.08 and clicks <= ref_clicks
            if click_reduction or echo_reduction:
                materially_better.append(c)
        if not materially_better:
            return reference
        return min(materially_better, key=lambda c: c["selection_score"])
    pool = passing or scored
    return min(pool, key=lambda c: c["selection_score"])


def _audio_sample_args(path: Path, start: float, dur: float, out: Path) -> list[str]:
    return ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(path), "-vn", "-ac", "2", "-ar", "48000", str(out)]
