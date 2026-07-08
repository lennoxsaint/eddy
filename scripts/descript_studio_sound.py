#!/usr/bin/env python3
"""Descript Studio Sound — audio only, self-contained.

Distilled from eddy-v2 `src/eddy_v2/audio.py`. The ONLY thing in Eddy V3 that talks to Descript,
and it only ever touches audio: extract WAV -> Descript Studio Sound -> parity check -> mux back
into the video. Never changes timing, content, or layout.

Usage:
  descript_studio_sound.py --in edited.mp4 --out final.mp4 [--intensity 100] [--work ./audio]
  descript_studio_sound.py --in edited.wav --out clean.m4a --audio-only

Env:
  DESCRIPT_API_KEY            required (Bearer token). Fails loud if missing.
  EDDY_DESCRIPT_API_BASE      optional override (default https://descriptapi.com/v1)
  EDDY_DESCRIPT_POLL_S        optional poll interval seconds (default 5)
  EDDY_FAKE_DESCRIPT=1        offline local ffmpeg approximation (dev only; NOT real Studio Sound)

Exit codes: 0 ok · 2 missing key · 3 parity failed · 4 api/other error
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("EDDY_DESCRIPT_API_BASE", "https://descriptapi.com/v1").rstrip("/")
MEDIA_NAME = "source-audio.wav"
POLL_S = float(os.environ.get("EDDY_DESCRIPT_POLL_S", "5"))


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


def studio_sound(wav: Path, out: Path, token: str, intensity: int) -> Path | None:
    if os.environ.get("EDDY_FAKE_DESCRIPT"):
        return fake_studio_sound(wav, out)
    prompt = (
        "Apply Studio Sound to the imported audio"
        + (f" at {intensity}% intensity" if intensity != 100 else "")
        + ". Do not remove words, change timing, add captions, or alter content."
    )
    import_payload = {
        "project_name": f"Eddy V3 Studio Sound {int(time.time())}",
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
    wait_job(str(agent["job_id"]), token)

    pub = api("POST", "/jobs/publish", token,
              {"project_id": project_id, "composition_id": composition_id,
               "media_type": "Audio", "access_level": "private"})
    pub_job = wait_job(str(pub["job_id"]), token)
    download_url = (pub_job.get("result") or {}).get("download_url") or pub_job.get("download_url")
    if not download_url:
        raise RuntimeError("descript_publish_missing_download_url")
    with urllib.request.urlopen(str(download_url), timeout=300) as r:
        out.write_bytes(r.read())
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
    if not token and not os.environ.get("EDDY_FAKE_DESCRIPT"):
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

        cleaned = work / "descript-studio-sound.m4a"
        result = studio_sound(src_wav, cleaned, token or "", args.intensity)
        if result is None or not parity_ok(src_wav, cleaned):
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
