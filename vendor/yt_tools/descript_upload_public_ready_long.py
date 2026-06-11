#!/usr/bin/env python3
"""Upload the QA-passed long video into the existing Descript project.

This script intentionally avoids printing credentials or signed upload URLs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path("/Users/yassybabes/YouTube")
EDIT_DIR = ROOT / "source/edit"
VIDEO = ROOT / "source/video.mp4"
QA = ROOT / "source/edit-qa.json"

PROJECT_ID = "25fc2e29-65fe-432d-9063-05899dc2be4c"
PROJECT_URL = f"https://web.descript.com/{PROJECT_ID}"
API_BASE = "https://descriptapi.com/v1"
SERVICE = "codex-descript-api-key"
ACCOUNT = "codex-descript"

MEDIA_ID = "Codex 2026-05-29 landed 2300 month client public-ready v16 QA pass.mp4"
COMPOSITION_NAME = "PUBLIC READY LONG - Codex landed 2300 month client - v16 QA pass"

REQUEST_PATH = EDIT_DIR / "descript-upload-public-ready-v16-request.json"
RESPONSE_PRIVATE_PATH = EDIT_DIR / "descript-upload-public-ready-v16-response.private.json"
RESPONSE_REDACTED_PATH = EDIT_DIR / "descript-upload-public-ready-v16-response.redacted.json"
STATUS_PATH = EDIT_DIR / "descript-upload-public-ready-v16-job-status.json"


def token() -> str:
    return subprocess.check_output(
        ["security", "find-generic-password", "-a", ACCOUNT, "-s", SERVICE, "-w"],
        text=True,
    ).strip()


def write_json(path: Path, data: Any, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if private:
        os.chmod(path, 0o600)


def redact_uploads(data: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(data))
    for item in clone.get("upload_urls", {}).values():
        if "upload_url" in item:
            item["upload_url"] = "REDACTED_SIGNED_UPLOAD_URL"
    return clone


def api_request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = None
    headers = {"Authorization": f"Bearer {token()}"}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"error": raw}
        parsed["http_status"] = exc.code
        return parsed


def put_file(url: str, file_path: Path) -> None:
    command = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "-X",
        "PUT",
        "-H",
        "Content-Type: application/octet-stream",
        "--upload-file",
        str(file_path),
        url,
    ]
    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"upload failed for {file_path.name}: {result.stderr.strip()}")


def import_body() -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "add_media": {
            MEDIA_ID: {
                "content_type": "video/mp4",
                "file_size": VIDEO.stat().st_size,
                "language": "en",
            }
        },
        "add_compositions": [
            {
                "name": COMPOSITION_NAME,
                "width": 1920,
                "height": 1080,
                "clips": [{"media": MEDIA_ID}],
            }
        ],
    }


def main() -> None:
    if not VIDEO.exists():
        raise SystemExit(f"missing-video {VIDEO}")
    qa = json.loads(QA.read_text(encoding="utf-8"))
    if qa.get("qa_status") != "pass":
        raise SystemExit("qa-status-not-pass")

    body = import_body()
    write_json(REQUEST_PATH, body)
    response = api_request("POST", "/jobs/import/project_media", body)
    write_json(RESPONSE_PRIVATE_PATH, response, private=True)
    write_json(RESPONSE_REDACTED_PATH, redact_uploads(response))
    if "job_id" not in response:
        print(f"upload-start-failed {RESPONSE_REDACTED_PATH}")
        raise SystemExit(1)

    upload_url = response.get("upload_urls", {}).get(MEDIA_ID, {}).get("upload_url")
    if not upload_url:
        print("missing-upload-url")
        raise SystemExit(1)

    print(f"uploading {MEDIA_ID} bytes={VIDEO.stat().st_size}")
    put_file(upload_url, VIDEO)

    job_id = response["job_id"]
    while True:
        status = api_request("GET", f"/jobs/{job_id}")
        write_json(STATUS_PATH, status)
        state = status.get("job_state")
        result_status = status.get("result", {}).get("status")
        print(f"import-status state={state} result={result_status}")
        if state == "stopped":
            if result_status != "success":
                raise SystemExit(1)
            created = status.get("result", {}).get("created_compositions", [])
            print(json.dumps({
                "status": "uploaded",
                "project_url": PROJECT_URL,
                "job_id": job_id,
                "created_compositions": created,
                "status_path": str(STATUS_PATH),
            }, indent=2))
            return
        time.sleep(30)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"descript-upload-error {exc}")
        raise SystemExit(1)
