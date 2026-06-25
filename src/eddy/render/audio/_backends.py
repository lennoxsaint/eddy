"""Heavy speech-enhancement backends (Resemble Enhance, DeepFilterNet) and discovery."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from eddy.config import AudioConfig
from eddy.studio_sound_env import DEFAULT_ENV, find_deep_filter, find_resemble_enhance


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
