"""Studio Sound: local audio enhancement (Descript-style) for rendered output.

Chain: [heavy speech enhancement backend if available] -> spectral click/clip repair ->
ffmpeg speech EQ (high-pass + presence lift + FFT denoise) -> two-pass EBU R128 loudnorm
to a YouTube target.

Applied to the RENDERED output's audio full-track (never the source — hard gate), then
remuxed with the untouched video stream. ffmpeg-only is the always-available path; heavy
models are used only when their backend/wrapper is installed and receipt-proven.
"""

from __future__ import annotations

from dataclasses import dataclass
import functools
import wave
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from eddy.config import AudioConfig
from eddy.media.ffmpeg import FFMPEG, run_ffmpeg
from eddy.studio_sound_env import DEFAULT_ENV, find_deep_filter, find_resemble_enhance


@dataclass(frozen=True)
class StudioSoundProfile:
    name: str
    dry_mix: float
    click_passes: int
    deesser_passes: int
    denoise: bool
    presence_gain_db: float
    compressor_ratio: float
    source_mode: str
    warm_low_shelf_db: float
    box_cut_db: float
    room_cut_db: float
    notes: str


STUDIO_SOUND_PROFILES: dict[str, StudioSoundProfile] = {
    "source_reference": StudioSoundProfile(
        name="source_reference",
        dry_mix=1.0,
        click_passes=0,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.0,
        compressor_ratio=1.0,
        source_mode="reference",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=0.0,
        notes="Do-not-harm candidate: preserve source/reference audio when cleanup makes it worse.",
    ),
    "warm_room_tame": StudioSoundProfile(
        name="warm_room_tame",
        dry_mix=0.52,
        click_passes=1,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.4,
        compressor_ratio=1.8,
        source_mode="raw",
        warm_low_shelf_db=2.2,
        box_cut_db=-2.0,
        room_cut_db=-1.8,
        notes="Source-first candidate: warmer/deeper voice, modest room cuts, very light click repair.",
    ),
    "warm_deep_tame": StudioSoundProfile(
        name="warm_deep_tame",
        dry_mix=0.50,
        click_passes=1,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.2,
        compressor_ratio=1.8,
        source_mode="raw",
        warm_low_shelf_db=3.0,
        box_cut_db=-2.3,
        room_cut_db=-2.1,
        notes="Source-first candidate: deeper/closer voice with stronger low-body support and room cuts.",
    ),
    "warm_click_tame": StudioSoundProfile(
        name="warm_click_tame",
        dry_mix=0.42,
        click_passes=2,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.7,
        compressor_ratio=2.0,
        source_mode="raw",
        warm_low_shelf_db=2.0,
        box_cut_db=-2.0,
        room_cut_db=-2.2,
        notes="Source-first candidate with stronger click repair while keeping the room natural.",
    ),
    "warm_model_10": StudioSoundProfile(
        name="warm_model_10",
        dry_mix=0.90,
        click_passes=1,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=0.4,
        compressor_ratio=1.8,
        source_mode="heavy",
        warm_low_shelf_db=1.8,
        box_cut_db=-1.6,
        room_cut_db=-1.6,
        notes="Mostly source audio with a tiny model-enhanced layer underneath; fails if it adds echo.",
    ),
    "natural_voice": StudioSoundProfile(
        name="natural_voice",
        dry_mix=0.28,
        click_passes=1,
        deesser_passes=0,
        denoise=False,
        presence_gain_db=1.2,
        compressor_ratio=2.0,
        source_mode="heavy",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=0.0,
        notes="Least processed candidate: keeps room/voice texture, repairs obvious clicks.",
    ),
    "click_rescue": StudioSoundProfile(
        name="click_rescue",
        dry_mix=0.18,
        click_passes=2,
        deesser_passes=1,
        denoise=False,
        presence_gain_db=1.8,
        compressor_ratio=2.4,
        source_mode="heavy",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=0.0,
        notes="Middle candidate: stronger mouth-click cleanup without FFT denoise.",
    ),
    "broadcast_clean": StudioSoundProfile(
        name="broadcast_clean",
        dry_mix=0.10,
        click_passes=2,
        deesser_passes=2,
        denoise=True,
        presence_gain_db=2.5,
        compressor_ratio=3.0,
        source_mode="heavy",
        warm_low_shelf_db=0.0,
        box_cut_db=0.0,
        room_cut_db=0.0,
        notes="Most processed candidate: reserved for noisy/echo-heavy source audio.",
    ),
}


@functools.lru_cache(maxsize=1)
def _available_audio_filters() -> frozenset[str]:
    try:
        proc = subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=15)
    except Exception:
        return frozenset()
    names = set(re.findall(r"^\s*[A-Z. ]{2,8}\s+([a-z0-9_]+)\s+", proc.stdout, re.MULTILINE))
    return frozenset(names)


def _speech_eq(cfg: AudioConfig) -> str:
    filters = _available_audio_filters()
    chain = [f"highpass=f={cfg.highpass_hz}"]
    if "afftdn" in filters:
        chain.append("afftdn=nf=-30")
    if cfg.mouth_click_cleanup:
        # These filters are optional across ffmpeg builds. Use them when present, skip silently when
        # absent so the studio-sound pass remains portable.
        if "adeclick" in filters:
            chain.append("adeclick")
            chain.append("adeclick")
        if "deesser" in filters:
            chain.append("deesser")
            chain.append("deesser")
    chain.append(f"equalizer=f={cfg.presence_hz}:t=q:w=2:g={cfg.presence_gain_db}")
    if "acompressor" in filters:
        chain.append(
            f"acompressor=threshold={cfg.compressor_threshold_db}dB:ratio={cfg.compressor_ratio}:attack=8:release=80"
        )
    chain.append("alimiter=limit=0.95")
    return ",".join(chain)


def _studio_sound_profile_names(cfg: AudioConfig) -> list[str]:
    profile = cfg.studio_sound_profile.strip().lower()
    aliases = {
        "strong_studio_sound": "broadcast_clean",
        "strong": "broadcast_clean",
        "balanced": "click_rescue",
        "natural": "natural_voice",
        "source": "source_reference",
        "reference": "source_reference",
        "preserve": "source_reference",
        "warm": "warm_room_tame",
        "deep": "warm_deep_tame",
        "room_tame": "warm_room_tame",
        "warm_click": "warm_click_tame",
    }
    if profile == "auto":
        names = [aliases.get(p.strip().lower(), p.strip().lower()) for p in cfg.studio_sound_candidate_profiles]
    else:
        names = [aliases.get(profile, profile)]
    valid = [name for name in names if name in STUDIO_SOUND_PROFILES]
    return valid or ["click_rescue"]


def _profile_polish_chain(profile: StudioSoundProfile, cfg: AudioConfig) -> str:
    if profile.source_mode == "reference":
        return "anull"
    filters = _available_audio_filters()
    chain = [f"highpass=f={max(45, min(cfg.highpass_hz, 65)) if profile.name.startswith('warm_') else cfg.highpass_hz}"]
    if profile.denoise and "afftdn" in filters:
        chain.append("afftdn=nf=-30")
    if cfg.mouth_click_cleanup and "adeclick" in filters:
        chain.extend(["adeclick"] * profile.click_passes)
    if cfg.mouth_click_cleanup and "deesser" in filters:
        chain.extend(["deesser"] * profile.deesser_passes)
    if profile.warm_low_shelf_db:
        chain.append(f"bass=g={profile.warm_low_shelf_db}:f=145:w=0.55")
    if profile.box_cut_db:
        chain.append(f"equalizer=f=900:t=q:w=1.3:g={profile.box_cut_db}")
    if profile.room_cut_db:
        chain.append(f"equalizer=f=3200:t=q:w=1.4:g={profile.room_cut_db}")
    chain.append(f"equalizer=f={cfg.presence_hz}:t=q:w=2:g={profile.presence_gain_db}")
    if "acompressor" in filters:
        chain.append(
            f"acompressor=threshold={cfg.compressor_threshold_db}dB:ratio={profile.compressor_ratio}:attack=8:release=80"
        )
    chain.append("alimiter=limit=0.95")
    return ",".join(chain)


def _echo_artifact_score(wav_path: Path, max_seconds: float = 600.0) -> float:
    """Approximate hollow/echo risk from post-speech tail energy.

    This is deliberately conservative: it does not pretend to be a perceptual audio judge. It gives
    Eddy a repeatable receipt that catches the failure Lennox flagged: an aggressive cleanup pass can
    reduce clicks while leaving a smeared room tail after syllables. Human listen still wins, but this
    stops obviously overcooked candidates from being selected automatically.
    """
    if not wav_path.exists():
        return 1.0
    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = max(1, wf.getnchannels())
            width = wf.getsampwidth()
            rate = wf.getframerate() or 48000
            frames_to_read = min(wf.getnframes(), int(max_seconds * rate))
            raw = wf.readframes(frames_to_read)
    except Exception:
        return 1.0
    if width not in (2, 4) or not raw:
        return 1.0
    import math
    import struct

    fmt = "<" + ("h" if width == 2 else "i") * (len(raw) // width)
    try:
        vals = struct.unpack(fmt, raw)
    except struct.error:
        return 1.0
    max_amp = float((2 ** (8 * width - 1)) - 1)
    mono = []
    for i in range(0, len(vals), channels):
        mono.append(sum(abs(v) for v in vals[i:i + channels]) / channels / max_amp)
    window = max(1, int(rate * 0.05))
    rms = []
    for i in range(0, len(mono), window):
        chunk = mono[i:i + window]
        if chunk:
            rms.append(math.sqrt(sum(v * v for v in chunk) / len(chunk)))
    if len(rms) < 8:
        return 0.0
    ordered = sorted(rms)
    floor = ordered[max(0, int(len(ordered) * 0.2) - 1)]
    loud = ordered[max(0, int(len(ordered) * 0.85) - 1)]
    threshold = max(floor * 4.0, loud * 0.22, 0.002)
    direct = 0.0
    tail = 0.0
    for i in range(1, len(rms) - 5):
        if rms[i] < threshold:
            continue
        if rms[i + 1] > rms[i] * 0.78:
            continue
        direct += rms[i]
        tail += sum(max(0.0, rms[j] - floor) for j in range(i + 1, i + 6))
    if direct <= 0:
        return 0.0
    return round(min(1.0, tail / (direct * 5.0)), 4)


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
        shutil.copy2(raw, out)
        clicks = _click_event_count(out, cfg.click_threshold)
        echo_score = _echo_artifact_score(out)
        return {
            "profile": profile.name,
            "path": str(out),
            "filter_chain": "anull",
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
    echo_gate_pass = (not cfg.require_echo_artifact_gate) or (
        echo_score <= cfg.echo_artifact_max_score and echo_score <= reference_echo_score + 0.015
    )
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


def _which_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    local = Path(sys.executable).parent / name
    if local.exists():
        return str(local)
    if os.name == "nt":
        local_exe = Path(sys.executable).parent / f"{name}.exe"
        if local_exe.exists():
            return str(local_exe)
    return None


def _click_event_count(wav_path: Path, threshold: float = 0.82, max_seconds: float = 600.0) -> int:
    """Crude local mouth-click detector: count isolated sample derivative spikes.

    This is not a perceptual model; it is an objective receipt that catches the obvious ASMR-style
    taps/clicks that survive a bad cleanup pass. A refractory window prevents one click from counting
    as hundreds of adjacent sample jumps.
    """
    if not wav_path.exists():
        return 0
    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = max(1, wf.getnchannels())
            width = wf.getsampwidth()
            rate = wf.getframerate() or 48000
            frames_to_read = min(wf.getnframes(), int(max_seconds * rate))
            raw = wf.readframes(frames_to_read)
    except Exception:
        return 0
    if width not in (2, 4) or not raw:
        return 0
    import struct

    fmt = "<" + ("h" if width == 2 else "i") * (len(raw) // width)
    try:
        vals = struct.unpack(fmt, raw)
    except struct.error:
        return 0
    max_amp = float((2 ** (8 * width - 1)) - 1)
    refractory = int(rate * 0.012) * channels
    last = -refractory
    count = 0
    for i in range(channels, len(vals)):
        jump = abs(vals[i] - vals[i - channels]) / max_amp
        if jump >= threshold and i - last >= refractory:
            count += 1
            last = i
    return count


def _spectral_repair_chain(cfg: AudioConfig) -> str:
    filters = _available_audio_filters()
    chain = []
    if "adeclick" in filters and cfg.mouth_click_cleanup:
        chain.append("adeclick")
        chain.append("adeclick")
    if "aclick" in filters and cfg.mouth_click_cleanup:
        chain.append("aclick")
    if "adeclip" in filters:
        chain.append("adeclip")
    if "deesser" in filters and cfg.mouth_click_cleanup:
        chain.append("deesser")
    # Smooth tiny room-tone discontinuities at cut joins without adding fake room tone.
    if "afade" in filters:
        chain.append("afade=t=in:st=0:d=0.015")
    return ",".join(chain)


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
    env_dir = Path(cfg.studio_sound_env).expanduser() if cfg.studio_sound_env else DEFAULT_ENV
    binary = find_deep_filter(env_dir) or _which_binary(cfg.deep_filter_binary)
    if not binary:
        return False
    # deepFilter writes <stem>_DeepFilterNet3.wav into the output dir. Some macOS/Torch combinations
    # leave multiprocessing children alive after the WAV is complete, so terminate once the expected
    # output is stable instead of hanging the whole edit.
    cmd = [binary, str(in_wav), "-o", str(out_wav.parent), "--log-level", "info"]
    expected = out_wav.parent / f"{in_wav.stem}_DeepFilterNet3.wav"
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 3600
    stable_seen_at: float | None = None
    last_size = -1
    while proc.poll() is None and time.monotonic() < deadline:
        if expected.exists():
            size = expected.stat().st_size
            if size > 44 and size == last_size:
                stable_seen_at = stable_seen_at or time.monotonic()
                if time.monotonic() - stable_seen_at > 2.0:
                    proc.terminate()
                    break
            else:
                stable_seen_at = None
                last_size = size
        time.sleep(0.25)
    if proc.poll() is None:
        proc.kill()
    stdout, stderr = proc.communicate(timeout=10)
    returncode = proc.returncode if proc.returncode is not None else -9
    if receipts is not None:
        receipts.log("deep_filter", exit_code=returncode, stdout_tail=stdout[-700:], stderr_tail=stderr[-700:])
    if not expected.exists() and returncode != 0:
        (Path(run_dir) / "deepfilter-failure.log").write_text(" ".join(cmd) + "\n\nSTDOUT\n" + stdout + "\n\nSTDERR\n" + stderr)
        return False
    produced = expected if expected.exists() else next(out_wav.parent.glob(f"{in_wav.stem}*DeepFilter*.wav"), None)
    if produced and produced != out_wav:
        produced.rename(out_wav)
    return out_wav.exists()


def _resemble_enhance(in_wav: Path, out_wav: Path, cfg: AudioConfig, run_dir: Path, receipts=None) -> bool:
    """Run Resemble Enhance from Eddy's Studio Sound env or PATH."""
    env_dir = Path(cfg.studio_sound_env).expanduser() if cfg.studio_sound_env else DEFAULT_ENV
    binary = find_resemble_enhance(env_dir)
    if not binary:
        return False

    input_dir = out_wav.parent / "resemble-in"
    output_dir = out_wav.parent / "resemble-out"
    shutil.rmtree(input_dir, ignore_errors=True)
    shutil.rmtree(output_dir, ignore_errors=True)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    staged = input_dir / "raw.wav"
    shutil.copy2(in_wav, staged)

    device = cfg.heavy_model_device
    if device == "auto":
        device = "mps" if platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"} else "cpu"
    cmd = [binary, "--device", device, str(input_dir), str(output_dir)]
    env = None
    if device == "mps":
        env = {**dict(os.environ), "PYTORCH_ENABLE_MPS_FALLBACK": "1"}
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=7200,
        env=env,
    )
    failure_log = Path(run_dir) / "resemble-enhance-failure.log"
    if receipts is not None:
        receipts.log("resemble_enhance", exit_code=proc.returncode, device=device, stderr_tail=proc.stderr[-700:])
    if proc.returncode != 0:
        failure_log.write_text(" ".join(cmd) + "\n\nSTDOUT\n" + proc.stdout + "\n\nSTDERR\n" + proc.stderr)
        return False
    produced = next(output_dir.rglob("*.wav"), None)
    if produced:
        produced.replace(out_wav)
    elif proc.stdout or proc.stderr:
        failure_log.write_text(" ".join(cmd) + "\n\nSTDOUT\n" + proc.stdout + "\n\nSTDERR\n" + proc.stderr)
    return out_wav.exists()


def _enhancer_status(cfg: AudioConfig) -> list[dict]:
    status = []
    env_dir = Path(cfg.studio_sound_env).expanduser() if cfg.studio_sound_env else DEFAULT_ENV
    for name in cfg.heavy_model_preference:
        key = name.lower()
        if key in {"resemble-enhance", "resemble_enhance", "resemble"}:
            status.append({"backend": name, "available": find_resemble_enhance(env_dir) is not None})
        elif key in {"deepfilternet", "deepfilter", "deep-filter"}:
            status.append({"backend": name, "available": (find_deep_filter(env_dir) or _which_binary(cfg.deep_filter_binary)) is not None})
        else:
            status.append({"backend": name, "available": _which_binary(name) is not None})
    return status


def _heavy_enhance(in_wav: Path, cfg: AudioConfig, run_dir: Path, receipts=None) -> tuple[Path, str, list[dict]]:
    attempts = _enhancer_status(cfg)
    for item in attempts:
        backend = item["backend"].lower()
        if backend in {"resemble-enhance", "resemble_enhance", "resemble"} and item["available"]:
            out = in_wav.parent / "enhanced-resemble.wav"
            if _resemble_enhance(in_wav, out, cfg, run_dir, receipts=receipts):
                item["applied"] = True
                return out, "resemble-enhance", attempts
            item["applied"] = False
            item["error"] = "resemble-enhance exited without output"
        elif backend in {"deepfilternet", "deepfilter", "deep-filter"} and item["available"]:
            out = in_wav.parent / "enhanced-deepfilternet.wav"
            if _deep_filter(in_wav, out, cfg, run_dir, receipts=receipts):
                item["applied"] = True
                return out, "deepfilternet", attempts
            item["applied"] = False
            item["error"] = "deep-filter exited without output"
        else:
            # ClearerVoice is tracked as a candidate heavy model. Its upstream interface is still
            # exposed to Eddy only after an explicit wrapper exists on PATH.
            item["applied"] = False
            if item["available"]:
                item["error"] = "backend wrapper detected but no stable Eddy CLI adapter yet"
            else:
                item["error"] = "not installed"
    return in_wav, "ffmpeg_only", attempts


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
        quality_gate_pass = click_gate_pass and echo_gate_pass and selected_loudness_gate_pass

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
                echo_artifact_score=selected.get("echo_artifact_score"),
                mouth_click_cleanup=cfg.mouth_click_cleanup,
                filter_chain=selected.get("filter_chain"),
                wet_dry_mix=selected.get("wet_dry_mix"),
                studio_sound_candidates=candidates,
                ab_samples=samples,
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
            "echo_artifact_score": selected.get("echo_artifact_score"),
            "ab_samples": samples,
            "mouth_click_cleanup": cfg.mouth_click_cleanup,
            "filter_chain": selected.get("filter_chain"),
            "wet_dry_mix": selected.get("wet_dry_mix"),
            "studio_sound_candidates": candidates,
        }
    except Exception as e:
        if receipts is not None:
            receipts.log("studio_sound", applied=False, error=str(e)[:300])
        return {"applied": False, "error": str(e)[:300]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
