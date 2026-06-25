"""Hardware-aware onboarding: detect machine + brains, recommend a tier, write config."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess

import httpx
import typer

from eddy import log
from eddy.config import load_config, update_config_sections

PING_SCHEMA = {
    "type": "object",
    "required": ["ok", "echo"],
    "properties": {"ok": {"type": "boolean"}, "echo": {"type": "string"}},
}

# Rough floor for a strong local editorial model (27B q4 + render headroom).
LOCAL_TIER_MIN_RAM_GB = 32
# A lighter machine can still run a smaller (~7-8B) local model — free + private, lower quality.
# Below this, a cloud brain is usually smoother (no hard 32GB cliff to a paid provider).
LOCAL_TIER_SMALL_RAM_GB = 16


def _linux_ram_gb(meminfo: str) -> int | None:
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            try:
                return round(int(line.split()[1]) / 2**20)  # kB -> GiB
            except (ValueError, IndexError):
                return None
    return None


def _linux_chip(cpuinfo: str) -> str:
    for line in cpuinfo.splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def _detect_hardware() -> dict:
    """Cross-platform hardware readout. Unknown RAM is None (NOT 0) so the recommender doesn't
    silently mis-tier a real machine it just couldn't measure."""
    info: dict = {"platform": platform.system(), "machine": platform.machine(), "chip": "unknown", "ram_gb": None}
    system = platform.system()
    try:
        if system == "Darwin":
            info["chip"] = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
            ).stdout.strip() or "unknown"
            mem = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
            info["ram_gb"] = round(int(mem.stdout.strip()) / 2**30)
        elif system == "Linux":
            from pathlib import Path as _P

            info["ram_gb"] = _linux_ram_gb(_P("/proc/meminfo").read_text())
            info["chip"] = _linux_chip(_P("/proc/cpuinfo").read_text())
        elif system == "Windows":
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))  # type: ignore[attr-defined]
            info["ram_gb"] = round(ms.ullTotalPhys / 2**30)
            info["chip"] = platform.processor() or "unknown"
    except Exception as exc:
        log.debug("hardware probe failed: %s", exc)  # leave chip='unknown', ram_gb=None — honest "couldn't measure"
    # psutil, if installed, is a clean cross-platform RAM source when the above couldn't measure
    if info["ram_gb"] is None:
        try:
            import psutil

            info["ram_gb"] = round(psutil.virtual_memory().total / 2**30)
        except Exception as exc:
            log.debug("psutil RAM probe failed: %s", exc)
    return info


def _ollama_models(base_url: str) -> list[str]:
    try:
        r = httpx.get(f"{base_url}/models", timeout=5)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]
    except Exception as exc:
        log.debug("model list probe failed for %s: %s", base_url, exc)
        return []


def detect() -> dict:
    cfg = load_config()
    hw = _detect_hardware()
    ollama_models = _ollama_models(cfg.provider.ollama.base_url)
    creds = {
        "anthropic_api": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
        "openai_api": bool(os.environ.get("OPENAI_API_KEY")),
        "codex_cli": shutil.which("codex") is not None,
        "claude_cli": shutil.which("claude") is not None,
        "gemini_thumbnails": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    }
    return {"hardware": hw, "ollama_models": ollama_models, "credentials": creds}


def _local_viability_note(models: list[str], ram: int, chip: str) -> str:
    if models and ram >= LOCAL_TIER_MIN_RAM_GB:
        return f" Local unlimited mode is also viable on {chip} with {ram}GB RAM."
    if models and ram >= LOCAL_TIER_SMALL_RAM_GB:
        return f" Local unlimited mode is available with a smaller model on {ram}GB RAM, but quality may be lower."
    if 0 < ram < LOCAL_TIER_SMALL_RAM_GB:
        return f" Local heavy models are likely tight on {ram}GB RAM."
    return ""


def recommend(found: dict) -> tuple[str, str]:
    """Return (provider_name, reason)."""
    hw, models, creds = found["hardware"], found["ollama_models"], found["credentials"]
    ram = hw.get("ram_gb") or 0  # None (unmeasured) -> 0 so we don't claim the local tier we can't confirm
    chip = hw.get("chip", "this machine")
    local_note = _local_viability_note(models, ram, chip)
    if creds["codex_cli"]:
        return "codex_cli", "Codex CLI is installed — defaulting to your ChatGPT/Codex brain for highest editorial quality." + local_note
    if creds["claude_cli"]:
        return "claude_cli", "Claude CLI is installed — defaulting to your Claude brain for highest editorial quality." + local_note
    if creds["openai_api"]:
        return "openai", "OpenAI API key found — defaulting to API editorial quality." + local_note
    if creds["anthropic_api"]:
        return "anthropic", "Anthropic API key found — defaulting to API editorial quality." + local_note
    if models and ram >= LOCAL_TIER_MIN_RAM_GB:
        return "ollama", f"{chip} with {ram}GB RAM runs a strong local model (27B) well — free unlimited editing."
    if models and ram >= LOCAL_TIER_SMALL_RAM_GB:
        # tiered: don't shove a 16-32GB machine onto a paid provider — a smaller local model is free + private
        return "ollama", (
            f"{chip} with {ram}GB RAM can run a smaller local model (~7-8B; lower quality than 27B) — "
            "still free + private. 32GB+ unlocks the best local quality."
        )
    light = f" (your {ram}GB RAM is light for a strong local model — a cloud brain may be smoother)" if 0 < ram < LOCAL_TIER_SMALL_RAM_GB else ""
    return "ollama", (
        "Nothing detected. Install Ollama (ollama.com) and run `ollama pull qwen3.6-27b` "
        "(or a smaller model on <32GB RAM), or set ANTHROPIC_API_KEY / OPENAI_API_KEY, "
        "or install the codex/claude CLI." + light
    )


def _ffmpeg_major(version_output: str) -> int | None:
    """Parse the major version from `ffmpeg -version` output, which always carries the
    'ffmpeg version ' prefix (e.g. 'ffmpeg version 8.0 ...', 'ffmpeg version n6.1.1 ...',
    'ffmpeg version 7.0.2-static ...'). Returns None if that prefix isn't present."""
    m = re.search(r"ffmpeg version n?(\d+)", version_output)
    return int(m.group(1)) if m else None


def preflight() -> list[dict]:
    """Environment checks a stranger needs BEFORE a 20GB model pull + a 50-min transcribe:
    ffmpeg present & >=8, ffprobe present, a usable video encoder, and enough free disk."""
    from eddy.media.ffmpeg import resolve_video_encoder

    checks: list[dict] = []

    ffmpeg = shutil.which("ffmpeg")
    major = None
    if ffmpeg:
        try:
            major = _ffmpeg_major(subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=10).stdout)
        except Exception as exc:
            log.debug("ffmpeg version probe failed: %s", exc)
            major = None
    ff_ok = bool(ffmpeg) and (major is None or major >= 8)
    checks.append({"check": "ffmpeg", "ok": ff_ok,
                   "detail": (f"v{major}" if major else "found") if ffmpeg else "NOT FOUND — install ffmpeg 8+"})

    checks.append({"check": "ffprobe", "ok": shutil.which("ffprobe") is not None,
                   "detail": "found" if shutil.which("ffprobe") else "NOT FOUND"})

    enc = resolve_video_encoder() if ffmpeg else None
    checks.append({"check": "video encoder", "ok": enc is not None, "detail": enc or "unavailable"})

    try:
        from eddy.studio_sound_env import status as studio_status

        ss = studio_status()
        checks.append({
            "check": "studio sound",
            "ok": bool(ss.get("quality_ready")),
            "detail": (
                f"DeepFilterNet ready: {ss.get('deep_filter')}"
                if ss.get("quality_ready")
                else "missing DeepFilterNet/Torch backend — run `eddy studio-sound install`"
            ),
        })
    except Exception as e:
        checks.append({"check": "studio sound", "ok": False, "detail": f"check failed: {str(e)[:100]}"})

    try:
        from pathlib import Path

        free_gb = round(shutil.disk_usage(Path.home()).free / 2**30)
        checks.append({"check": "free disk", "ok": free_gb >= 5, "detail": f"{free_gb}GB free"})
    except Exception as exc:
        log.debug("free-disk probe failed: %s", exc)
        checks.append({"check": "free disk", "ok": True, "detail": "unknown"})

    return checks


def ping_provider(name: str) -> dict:
    from eddy.providers.base import get_provider

    cfg = load_config()
    try:
        p = get_provider(cfg, name)
        text = p.complete([{"role": "user", "content": "Reply with exactly: pong"}], max_tokens=64)
        structured = p.complete(
            [
                {
                    "role": "user",
                    "content": 'Return ONLY a JSON object: {"ok": true, "echo": "eddy"}',
                }
            ],
            schema=PING_SCHEMA,
            max_tokens=128,
        )
        return {"provider": name, "ok": True, "text": str(text)[:60], "structured": structured}
    except Exception as e:
        return {"provider": name, "ok": False, "error": f"{type(e).__name__}: {e}"}


def run_doctor(ping: bool = False, all_providers: bool = False, write: bool = True) -> dict:
    found = detect()
    provider, reason = recommend(found)

    hw = found["hardware"]
    typer.echo(f"machine     {hw.get('chip', '?')} · {hw.get('ram_gb', '?')}GB RAM")
    typer.echo(f"ollama      {', '.join(found['ollama_models']) or 'not running / no models'}")
    creds = found["credentials"]
    typer.echo("brains      " + ", ".join(k for k, v in creds.items() if v) if any(creds.values()) else "brains      none detected")
    typer.echo(f"recommend   {provider} — {reason}")

    for c in preflight():
        mark = "ok  " if c["ok"] else "FAIL"
        typer.echo(f"{c['check']:11} {mark} {c['detail']}")

    if write:
        sections: dict = {"provider": {"active": provider}}
        if provider == "ollama" and found["ollama_models"]:
            preferred = [m for m in found["ollama_models"] if "qwen" in m.lower()]
            sections["provider"]["ollama"] = {"model": (preferred or found["ollama_models"])[0]}
        path = update_config_sections(sections)
        typer.echo(f"config      wrote {path}")

    results = []
    if ping or all_providers:
        names = (
            ["ollama", "anthropic", "openai", "codex_cli", "claude_cli"]
            if all_providers
            else [provider]
        )
        for n in names:
            res = ping_provider(n)
            results.append(res)
            status = "OK " if res["ok"] else "FAIL"
            detail = res.get("structured") or res.get("error", "")
            typer.echo(f"ping {n:11} {status} {json.dumps(detail) if isinstance(detail, dict) else detail}")

    return {"found": found, "recommend": provider, "pings": results}
