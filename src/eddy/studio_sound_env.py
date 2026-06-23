"""Install and inspect Eddy's heavy local Studio Sound backend.

Eddy's default Studio Sound route is DeepFilterNet in the active Eddy environment: it is local,
repeatable, and practical enough to provision during repo/skill install. Resemble Enhance remains
available as an optional experimental backend because its dependency stack is heavier and less
portable. Source media stays local; only model packages/weights are downloaded.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_ENV = Path("~/.cache/eddy/studio-sound/resemble-enhance-py311").expanduser()
PYTHON_CANDIDATES = ("python3.11", "python3.10", "python3.9")
PACKAGE_SPEC = "resemble-enhance"
DEEPFILTER_PACKAGES = ("deepfilternet", "torch==2.2.2", "torchaudio==2.2.2", "soundfile")


def _bin_dir(env_dir: Path) -> Path:
    return env_dir / ("Scripts" if os.name == "nt" else "bin")


def env_python(env_dir: Path = DEFAULT_ENV) -> Path:
    return _bin_dir(env_dir) / ("python.exe" if os.name == "nt" else "python")


def resemble_binary(env_dir: Path = DEFAULT_ENV) -> Path:
    return _bin_dir(env_dir) / ("resemble-enhance.exe" if os.name == "nt" else "resemble-enhance")


def find_resemble_enhance(env_dir: Path = DEFAULT_ENV) -> str | None:
    local = resemble_binary(env_dir)
    if local.exists():
        return str(local)
    return shutil.which("resemble-enhance")


def find_deep_filter() -> str | None:
    # Do not resolve sys.executable here: venv Python is often a symlink to the Homebrew/system
    # interpreter, and resolving it would look beside the base Python instead of beside Eddy's venv.
    local = _bin_dir(Path(sys.executable).parent.parent) / ("deepFilter.exe" if os.name == "nt" else "deepFilter")
    if local.exists():
        return str(local)
    sibling = Path(sys.executable).parent / ("deepFilter.exe" if os.name == "nt" else "deepFilter")
    if sibling.exists():
        return str(sibling)
    return shutil.which("deepFilter")


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def find_backend_python() -> str | None:
    override = os.environ.get("EDDY_STUDIO_SOUND_PYTHON")
    if override:
        return override if shutil.which(override) or Path(override).exists() else None
    for name in PYTHON_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def status(env_dir: Path = DEFAULT_ENV) -> dict:
    deep_filter = find_deep_filter()
    resemble = find_resemble_enhance(env_dir)
    py = find_backend_python()
    git_lfs = shutil.which("git-lfs") or shutil.which("git-lfs.exe")
    torch_ready = _module_available("torch")
    torchaudio_ready = _module_available("torchaudio")
    soundfile_ready = _module_available("soundfile")
    return {
        "env_dir": str(env_dir),
        "backend_python": py,
        "env_exists": env_dir.exists(),
        "python_exists": env_python(env_dir).exists(),
        "default_backend": "deepfilternet",
        "deep_filter": deep_filter,
        "torch": torch_ready,
        "torchaudio": torchaudio_ready,
        "soundfile": soundfile_ready,
        "rust": shutil.which("rustc") or shutil.which("cargo"),
        "resemble_enhance": resemble,
        "git_lfs": git_lfs,
        "quality_ready": bool(deep_filter and torch_ready and torchaudio_ready and soundfile_ready),
        "install_command": "eddy studio-sound install",
    }


def install_deepfilternet(force: bool = False) -> dict:
    """Install/update Eddy's default Studio Sound backend in the active environment."""
    if not shutil.which("rustc") and not shutil.which("cargo"):
        return {
            "ok": False,
            "stage": "rust",
            "error": "Rust is required to build DeepFilterNet's native audio extension when a wheel is not available.",
            "next_action": "Install Rust (`brew install rust` on macOS or https://rustup.rs), then rerun `eddy studio-sound install`.",
        }
    pip = [sys.executable, "-m", "pip"]
    packages = list(DEEPFILTER_PACKAGES)
    cmd = pip + ["install", "--upgrade" if force else "--upgrade", *packages]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    logs = [{"cmd": cmd, "returncode": proc.returncode, "stdout_tail": proc.stdout[-1200:], "stderr_tail": proc.stderr[-1600:]}]
    if proc.returncode:
        return {
            "ok": False,
            "stage": "pip-deepfilternet",
            "logs": logs,
            "error": proc.stderr[-1800:] or proc.stdout[-1800:],
            "next_action": "Fix the DeepFilterNet/Torch dependency error above, then rerun `eddy studio-sound install`.",
        }
    st = status()
    return {"ok": bool(st.get("quality_ready")), "stage": "deepfilternet", "status": st, "logs": logs}


def install_studio_sound(
    env_dir: Path = DEFAULT_ENV,
    force: bool = False,
    include_resemble: bool = False,
) -> dict:
    """Provision Eddy's local Studio Sound stack.

    DeepFilterNet is the required default. Resemble Enhance can be installed as an additional backend
    for experiments, but a failed optional install does not make the required backend disappear.
    """
    deep = install_deepfilternet(force=force)
    logs = {"deepfilternet": deep}
    if not deep.get("ok"):
        return deep
    if include_resemble:
        logs["resemble_enhance"] = install_resemble_enhance(env_dir=env_dir, force=force)
    st = status(env_dir)
    return {"ok": bool(st.get("quality_ready")), "stage": "done", "status": st, "logs": logs}


def install_resemble_enhance(env_dir: Path = DEFAULT_ENV, force: bool = False) -> dict:
    """Create/update the isolated Studio Sound env and install Resemble Enhance."""
    if force and env_dir.exists():
        shutil.rmtree(env_dir)
    py = find_backend_python()
    if not py:
        return {
            "ok": False,
            "stage": "python",
            "error": "Python 3.9-3.11 is required for the Resemble Enhance backend.",
            "next_action": "Install Python 3.11, or set EDDY_STUDIO_SOUND_PYTHON to a compatible interpreter.",
        }
    if not (shutil.which("git-lfs") or shutil.which("git-lfs.exe")):
        return {
            "ok": False,
            "stage": "git-lfs",
            "error": "git-lfs is required so Resemble Enhance can download model weights.",
            "next_action": "Install Git LFS (`brew install git-lfs && git lfs install` on macOS), then rerun `eddy studio-sound install`.",
        }
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    if not env_python(env_dir).exists():
        proc = subprocess.run([py, "-m", "venv", str(env_dir)], capture_output=True, text=True, timeout=600)
        if proc.returncode:
            return {
                "ok": False,
                "stage": "venv",
                "error": proc.stderr[-1200:] or proc.stdout[-1200:],
                "next_action": "Fix the Python venv error, then rerun `eddy studio-sound install`.",
            }

    pip = [str(env_python(env_dir)), "-m", "pip"]
    commands = [
        pip + ["install", "--upgrade", "pip", "setuptools", "wheel"],
        pip + ["install", "--upgrade", PACKAGE_SPEC],
    ]
    logs = []
    for cmd in commands:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        logs.append({"cmd": cmd, "returncode": proc.returncode, "stdout_tail": proc.stdout[-1000:], "stderr_tail": proc.stderr[-1400:]})
        if proc.returncode:
            return {
                "ok": False,
                "stage": "pip",
                "logs": logs,
                "error": proc.stderr[-1600:] or proc.stdout[-1600:],
                "next_action": "Install the missing system dependency reported above, then rerun `eddy studio-sound install`.",
            }
    return {"ok": bool(find_resemble_enhance(env_dir)), "stage": "done", "status": status(env_dir), "logs": logs}


def main() -> None:
    import json

    result = install_studio_sound()
    print(json.dumps(result, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
