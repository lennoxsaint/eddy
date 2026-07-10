#!/usr/bin/env python3
"""Descript Studio Sound — audio only, self-contained.

Distilled from the proven legacy audio path. This is the only Eddy component that talks to Descript,
and it only ever touches audio: extract WAV -> Descript Studio Sound -> parity check -> mux back
into the video. Never changes timing, content, or layout.

Usage:
  descript_studio_sound.py --in edited.mp4 --out final.mp4 [--intensity 100] [--work ./audio]
  descript_studio_sound.py --in edited.wav --out clean.m4a --audio-only

Env:
  DESCRIPT_API_KEY            required (Bearer token). Fails loud if missing.
  EDDY_DESCRIPT_API_BASE      optional override (default https://descriptapi.com/v1)
  EDDY_DESCRIPT_POLL_S        optional poll interval seconds (default 5)
  EDDY_DESCRIPT_CONNECTOR     optional host connector command; receives input/output/receipt args
  EDDY_FAKE_DESCRIPT=1        offline local ffmpeg approximation (dev only; NOT real Studio Sound)

Exit codes: 0 ok · 2 missing key · 3 parity/effect-survival failed · 4 api/other error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eddy.audio_effect import EffectCalibration, evaluate_effect_survival  # noqa: E402

API_BASE = os.environ.get("EDDY_DESCRIPT_API_BASE", "https://descriptapi.com/v1").rstrip("/")
MEDIA_NAME = "source-audio.wav"
POLL_S = float(os.environ.get("EDDY_DESCRIPT_POLL_S", "5"))
MAX_EFFECT_ATTEMPTS = 2


def log(event: str, **kw) -> None:
    """One JSON line per event on stderr — secret-safe receipts."""
    print(json.dumps({"event": event, **kw}), file=sys.stderr, flush=True)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out) if out else 0.0


def extract_wav(video: Path, wav: Path) -> Path:
    wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "48000",
         "-c:a", "pcm_s16le", str(wav)],
        check=True, capture_output=True,
    )
    return wav


def api(method: str, path: str, token: str, payload: dict | None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{API_BASE}{path}", data=body, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[-500:]
        log("descript_api_error", path=path, status=e.code, detail=detail)
        raise RuntimeError(f"descript_api_failed:{path}:{e.code}") from e


def upload(url: str, wav: Path) -> None:
    req = urllib.request.Request(
        url, data=wav.read_bytes(), method="PUT",
        headers={"Content-Type": "application/octet-stream"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        log("descript_upload_done", status=getattr(r, "status", None), bytes=wav.stat().st_size)


def wait_job(job_id: str, token: str, timeout_s: int = 1800) -> dict:
    started = time.monotonic()
    while True:
        job = api("GET", f"/jobs/{job_id}", token, None)
        state = job.get("job_state")
        if state == "stopped":
            result = job.get("result") or {}
            if isinstance(result, dict) and result.get("status") != "success":
                raise RuntimeError(f"descript_job_failed:{job_id}:{result.get('status')}")
            return job
        if time.monotonic() - started > timeout_s:
            raise RuntimeError(f"descript_job_timeout:{job_id}")
        time.sleep(POLL_S)


def studio_sound_prompt(intensity: int) -> str:
    return (
        f"Add Studio Sound to every clip at {intensity}% intensity. "
        "Confirm Studio Sound is enabled on the complete source audio before finishing. "
        "Do not remove words, change timing, add captions, or alter content."
    )


def fake_studio_sound(wav: Path, out: Path) -> Path:
    """Dev-only offline approximation. NOT real Studio Sound — never ship this output."""
    log("descript_fake", note="local ffmpeg approximation, not real studio sound")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav), "-af",
         "highpass=f=80,afftdn=nf=-25,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
         "loudnorm=I=-14:TP=-1.5:LRA=11",
         "-c:a", "aac", "-b:a", "192k", str(out)],
        check=True, capture_output=True,
    )
    return out


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def host_connector_sound(wav: Path, out: Path, command: str) -> Path:
    """Invoke an authenticated host adapter without exposing its credentials to Eddy."""

    receipt = out.with_suffix(out.suffix + ".provider.json")
    result = subprocess.run(
        [
            *shlex.split(command),
            "--input-wav",
            str(wav),
            "--output-audio",
            str(out),
            "--receipt",
            str(receipt),
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(f"descript_host_connector_failed:{result.stderr[-500:]}")
    if not out.exists() or not receipt.exists():
        raise RuntimeError("descript_host_connector_artifact_missing")
    payload = json.loads(receipt.read_text())
    required = ("provider", "project_id", "composition_id", "source_sha256", "output_sha256")
    if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
        raise RuntimeError("descript_host_connector_receipt_invalid")
    if payload["provider"] != "descript_host_connector" or payload.get("access_level") != "private":
        raise RuntimeError("descript_host_connector_provenance_invalid")
    if payload["source_sha256"] != sha256(wav) or payload["output_sha256"] != sha256(out):
        raise RuntimeError("descript_host_connector_hash_mismatch")
    log(
        "descript_provider",
        provider=payload["provider"],
        project_id=payload["project_id"],
        composition_id=payload["composition_id"],
        access_level="private",
    )
    return out


def studio_sound(wav: Path, out: Path, token: str, intensity: int) -> Path | None:
    if os.environ.get("EDDY_FAKE_DESCRIPT"):
        return fake_studio_sound(wav, out)
    connector = os.environ.get("EDDY_DESCRIPT_CONNECTOR")
    if connector:
        return host_connector_sound(wav, out, connector)
    prompt = studio_sound_prompt(intensity)
    import_payload = {
        "project_name": f"Eddy Studio Sound {int(time.time())}",
        "add_media": {MEDIA_NAME: {"content_type": "audio/wav", "file_size": wav.stat().st_size}},
        "add_compositions": [{"name": "Studio Sound Audio", "clips": [{"media": MEDIA_NAME}]}],
    }
    resp = api("POST", "/jobs/import/project_media", token, import_payload)
    upload_url = ((resp.get("upload_urls") or {}).get(MEDIA_NAME) or {}).get("upload_url")
    if not upload_url:
        raise RuntimeError("descript_import_missing_upload_url")
    log("descript_import", job_id=resp.get("job_id"), project_id=resp.get("project_id"))
    upload(upload_url, wav)
    import_job = wait_job(str(resp["job_id"]), token)
    comps = (import_job.get("result") or {}).get("created_compositions") or []
    if not comps:
        raise RuntimeError("descript_import_missing_composition")
    composition_id = str(comps[0]["id"])
    project_id = str(import_job.get("project_id") or resp.get("project_id"))

    agent = api("POST", "/jobs/agent", token,
                {"project_id": project_id, "composition_id": composition_id, "prompt": prompt})
    log("descript_agent_started", job_id=agent.get("job_id"))
    agent_job = wait_job(str(agent["job_id"]), token)
    agent_result = agent_job.get("result") or {}
    log(
        "descript_agent_result",
        job_id=agent.get("job_id"),
        status=agent_result.get("status"),
        project_changed=bool(agent_result.get("project_changed")),
        agent_response=str(agent_result.get("agent_response") or "")[:500],
        ai_credits_used=agent_result.get("ai_credits_used"),
        resolved_model=agent_result.get("resolved_model") or agent_job.get("resolved_model"),
    )
    if not agent_result.get("project_changed"):
        raise RuntimeError("descript_agent_made_no_change")

    pub = api("POST", "/jobs/publish", token,
              {"project_id": project_id, "composition_id": composition_id,
               "media_type": "Audio", "access_level": "private"})
    pub_job = wait_job(str(pub["job_id"]), token)
    download_url = (pub_job.get("result") or {}).get("download_url") or pub_job.get("download_url")
    if not download_url:
        raise RuntimeError("descript_publish_missing_download_url")
    with urllib.request.urlopen(str(download_url), timeout=300) as r:
        out.write_bytes(r.read())
    log(
        "descript_provider",
        provider="descript_api",
        project_id=project_id,
        composition_id=composition_id,
        access_level="private",
    )
    log("descript_download_done", out=str(out), bytes=out.stat().st_size)
    return out


def parity_ok(src_wav: Path, cleaned: Path) -> bool:
    a, b = ffprobe_duration(src_wav), ffprobe_duration(cleaned)
    delta = abs(a - b)
    tol = max(1.0, a * 0.01)
    ok = cleaned.exists() and b > 0 and delta <= tol
    log("audio_parity", status="pass" if ok else "failed",
        source_s=round(a, 3), out_s=round(b, 3), delta_s=round(delta, 3), tol_s=round(tol, 3))
    return ok


def effect_survival_ok(src_wav: Path, cleaned: Path, work: Path) -> bool:
    decoded = work / "descript-export-proof.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(cleaned), "-vn", "-ac", "1", "-ar", "48000",
            "-c:a", "pcm_s16le", str(decoded),
        ],
        check=True,
        capture_output=True,
    )
    result = evaluate_effect_survival(src_wav, decoded, EffectCalibration.default())
    log(
        "descript_effect_survival",
        status="pass" if result.passed else "failed",
        blockers=list(result.blockers),
        metrics=result.metrics,
    )
    return result.passed


def retryable_provider_error(error: BaseException) -> bool:
    reason = str(error)
    if reason.startswith("descript_api_failed:"):
        try:
            status = int(reason.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            return False
        return status in {408, 409, 425, 429, 500, 502, 503, 504}
    return isinstance(error, (TimeoutError, urllib.error.URLError)) or reason.startswith(
        (
            "descript_job_timeout:",
            "descript_job_failed:",
            "descript_import_missing_",
            "descript_publish_missing_",
            "descript_agent_made_no_change",
        )
    )


def studio_sound_with_effect_retry(
    src_wav: Path,
    work: Path,
    token: str,
    intensity: int,
    *,
    max_attempts: int = MAX_EFFECT_ATTEMPTS,
) -> Path | None:
    """Retry one fresh provider render only when the effect is missing from export."""

    for attempt in range(1, max_attempts + 1):
        attempt_work = work if attempt == 1 else work / f"retry-{attempt}"
        attempt_work.mkdir(parents=True, exist_ok=True)
        cleaned = attempt_work / "descript-studio-sound.m4a"
        try:
            result = studio_sound(src_wav, cleaned, token, intensity)
        except (RuntimeError, TimeoutError, urllib.error.URLError) as error:
            if attempt >= max_attempts or not retryable_provider_error(error):
                raise
            log(
                "descript_provider_retry",
                failed_attempt=attempt,
                next_attempt=attempt + 1,
                reason=str(error).split(":", 1)[0],
            )
            continue
        if result is None or not parity_ok(src_wav, result):
            return None
        if effect_survival_ok(src_wav, result, attempt_work):
            return result
        if attempt < max_attempts:
            log(
                "descript_effect_retry",
                failed_attempt=attempt,
                next_attempt=attempt + 1,
                reason="descript_effect_not_rendered",
            )
    return None


def mux(video: Path, cleaned_audio: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-i", str(cleaned_audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(out)],
        check=True, capture_output=True,
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Descript Studio Sound (audio only).")
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--intensity", type=int, default=100)
    ap.add_argument("--work", default=None, help="scratch dir for the extracted WAV")
    ap.add_argument("--audio-only", action="store_true",
                    help="input is already audio; write cleaned audio to --out, skip mux")
    args = ap.parse_args()

    token = os.environ.get("DESCRIPT_API_KEY")
    if (
        not token
        and not os.environ.get("EDDY_FAKE_DESCRIPT")
        and not os.environ.get("EDDY_DESCRIPT_CONNECTOR")
    ):
        log("blocked", reason="DESCRIPT_API_KEY missing")
        print("ERROR: DESCRIPT_API_KEY is not set. Studio Sound is non-negotiable — export the "
              "key (or set EDDY_FAKE_DESCRIPT=1 for a dev-only offline approximation).",
              file=sys.stderr)
        return 2

    inp, out = Path(args.inp), Path(args.out)
    work = Path(args.work) if args.work else (out.parent / "audio")
    work.mkdir(parents=True, exist_ok=True)

    try:
        if args.audio_only and inp.suffix.lower() in {".wav"}:
            src_wav = inp
        else:
            src_wav = extract_wav(inp, work / MEDIA_NAME)

        cleaned = studio_sound_with_effect_retry(
            src_wav,
            work,
            token or "",
            args.intensity,
        )
        if cleaned is None:
            return 3

        if args.audio_only:
            if cleaned != out:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(cleaned.read_bytes())
        else:
            mux(inp, cleaned, out)
        log("done", out=str(out))
        return 0
    except Exception as exc:  # noqa: BLE001 - surface a clean receipt, non-zero exit
        log("error", error=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
