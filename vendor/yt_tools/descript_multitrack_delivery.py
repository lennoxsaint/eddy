#!/usr/bin/env python3
"""Create/publish Descript multitrack delivery without printing credentials."""

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
EXPORT_DIR = ROOT / "source/exports"
CAMERA = ROOT / "source/work/camera_long_cut.mp4"
SCREEN = ROOT / "source/work/screen_long_cut_synced.mp4"
PROJECT_ID = "25fc2e29-65fe-432d-9063-05899dc2be4c"
API_BASE = "https://descriptapi.com/v1"
SERVICE = "codex-descript-api-key"
ACCOUNT = "codex-descript"

CAMERA_ID = "Codex cleaned camera cut multitrack 2026-05-31 v2.mp4"
SCREEN_ID = "Codex cleaned screen cut synced multitrack 2026-05-31 v2.mp4"
SEQUENCE_ID = "Codex cleaned multitrack sequence camera+screen 2026-05-31 v2"
COMPOSITION_NAME = "EDITABLE MULTITRACK CLEAN CUT - 2026-05-31 v2"

REQUEST_PATH = EDIT_DIR / "descript-create-multitrack-v2-request.json"
RESPONSE_PATH = EDIT_DIR / "descript-create-multitrack-v2-response.private.json"
RESPONSE_REDACTED_PATH = EDIT_DIR / "descript-create-multitrack-v2-response.redacted.json"
STATUS_PATH = EDIT_DIR / "descript-create-multitrack-v2-job-status.json"
PUBLISH_REQUEST_PATH = EDIT_DIR / "descript-publish-multitrack-v2-request.json"
PUBLISH_RESPONSE_PATH = EDIT_DIR / "descript-publish-multitrack-v2-response.json"
PUBLISH_STATUS_PATH = EDIT_DIR / "descript-publish-multitrack-v2-job-status.private.json"
PUBLISH_STATUS_REDACTED_PATH = EDIT_DIR / "descript-publish-multitrack-v2-job-status.redacted.json"
DESCRIPT_EXPORT_PATH = EXPORT_DIR / "Codex-2026-05-29-landed-2300-month-client-descript-multitrack-export.mp4"
POLISHED = EXPORT_DIR / "Codex-2026-05-29-landed-2300-month-client-long-sop-polished-local.mp4"
POLISHED_ID = "Codex SOP polished final long 2026-05-31.mp4"
POLISHED_COMPOSITION_NAME = "SOP POLISHED FINAL LONG - 2026-05-31"
POLISHED_REQUEST_PATH = EDIT_DIR / "descript-import-polished-final-request.json"
POLISHED_RESPONSE_PATH = EDIT_DIR / "descript-import-polished-final-response.private.json"
POLISHED_RESPONSE_REDACTED_PATH = EDIT_DIR / "descript-import-polished-final-response.redacted.json"
POLISHED_STATUS_PATH = EDIT_DIR / "descript-import-polished-final-job-status.json"
POLISHED_EXPORT_PATH = EXPORT_DIR / "Codex-2026-05-29-landed-2300-month-client-descript-polished-final-export.mp4"


def token() -> str:
    return subprocess.check_output(
        ["security", "find-generic-password", "-a", ACCOUNT, "-s", SERVICE, "-w"],
        text=True,
    ).strip()


def write_private(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def redact_uploads(data: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(data))
    for item in clone.get("upload_urls", {}).values():
        if "upload_url" in item:
            item["upload_url"] = "REDACTED_SIGNED_UPLOAD_URL"
    return clone


def redact_download(data: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(data))
    result = clone.get("result")
    if isinstance(result, dict) and "download_url" in result:
        result["download_url"] = "REDACTED_SIGNED_DOWNLOAD_URL"
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
            SCREEN_ID: {
                "content_type": "video/mp4",
                "file_size": SCREEN.stat().st_size,
                "language": "en",
            },
            CAMERA_ID: {
                "content_type": "video/mp4",
                "file_size": CAMERA.stat().st_size,
                "language": "en",
            },
            SEQUENCE_ID: {
                "tracks": [
                    {"media": SCREEN_ID, "offset": 0},
                    {"media": CAMERA_ID, "offset": 0},
                ],
            },
        },
        "add_compositions": [
            {
                "name": COMPOSITION_NAME,
                "width": 1920,
                "height": 1080,
                "clips": [{"media": SEQUENCE_ID}],
            }
        ],
    }


def start_import() -> None:
    body = import_body()
    write_json(REQUEST_PATH, body)
    response = api_request("POST", "/jobs/import/project_media", body)
    write_private(RESPONSE_PATH, response)
    write_json(RESPONSE_REDACTED_PATH, redact_uploads(response))
    if "job_id" not in response:
        print(f"import-start-failed {RESPONSE_REDACTED_PATH}")
        sys.exit(1)
    uploads = response.get("upload_urls", {})
    for media_id, file_path in [(SCREEN_ID, SCREEN), (CAMERA_ID, CAMERA)]:
        upload_url = uploads.get(media_id, {}).get("upload_url")
        if not upload_url:
            print(f"missing-upload-url {media_id}")
            sys.exit(1)
        print(f"uploading {media_id} bytes={file_path.stat().st_size}")
        put_file(upload_url, file_path)
    print(f"import-job {response['job_id']}")


def upload_existing(media_ids: set[str] | None = None) -> None:
    response = json.loads(RESPONSE_PATH.read_text(encoding="utf-8"))
    uploads = response.get("upload_urls", {})
    for media_id, file_path in [(SCREEN_ID, SCREEN), (CAMERA_ID, CAMERA)]:
        if media_ids is not None and media_id not in media_ids:
            continue
        upload_url = uploads.get(media_id, {}).get("upload_url")
        if not upload_url:
            print(f"missing-upload-url {media_id}")
            sys.exit(1)
        print(f"uploading {media_id} bytes={file_path.stat().st_size}")
        put_file(upload_url, file_path)
    print(f"import-job {response['job_id']}")


def poll_import() -> dict[str, Any]:
    response = json.loads(RESPONSE_PATH.read_text(encoding="utf-8"))
    job_id = response["job_id"]
    while True:
        status = api_request("GET", f"/jobs/{job_id}")
        write_json(STATUS_PATH, status)
        state = status.get("job_state")
        result_status = status.get("result", {}).get("status")
        print(f"import-status state={state} result={result_status}")
        if state == "stopped":
            return status
        time.sleep(30)


def publish(composition_id: str) -> dict[str, Any]:
    body = {
        "project_id": PROJECT_ID,
        "composition_id": composition_id,
        "media_type": "Video",
        "resolution": "1080p",
        "access_level": "private",
    }
    write_json(PUBLISH_REQUEST_PATH, body)
    response = api_request("POST", "/jobs/publish", body)
    write_json(PUBLISH_RESPONSE_PATH, response)
    if "job_id" not in response:
        print(f"publish-start-failed {PUBLISH_RESPONSE_PATH}")
        return response
    job_id = response["job_id"]
    while True:
        status = api_request("GET", f"/jobs/{job_id}")
        write_private(PUBLISH_STATUS_PATH, status)
        write_json(PUBLISH_STATUS_REDACTED_PATH, redact_download(status))
        state = status.get("job_state")
        result_status = status.get("result", {}).get("status")
        print(f"publish-status state={state} result={result_status}")
        if state == "stopped":
            return status
        time.sleep(30)


def download_publish(status: dict[str, Any]) -> None:
    url = status.get("result", {}).get("download_url")
    if not url:
        print("no-download-url")
        return
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--location", "-o", str(DESCRIPT_EXPORT_PATH), url],
        check=True,
    )
    print(f"downloaded {DESCRIPT_EXPORT_PATH}")


def import_polished_body() -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "add_media": {
            POLISHED_ID: {
                "content_type": "video/mp4",
                "file_size": POLISHED.stat().st_size,
                "language": "en",
            }
        },
        "add_compositions": [
            {
                "name": POLISHED_COMPOSITION_NAME,
                "width": 1920,
                "height": 1080,
                "clips": [{"media": POLISHED_ID}],
            }
        ],
    }


def import_polished() -> dict[str, Any]:
    body = import_polished_body()
    write_json(POLISHED_REQUEST_PATH, body)
    response = api_request("POST", "/jobs/import/project_media", body)
    write_private(POLISHED_RESPONSE_PATH, response)
    write_json(POLISHED_RESPONSE_REDACTED_PATH, redact_uploads(response))
    if "job_id" not in response:
        print(f"polished-import-start-failed {POLISHED_RESPONSE_REDACTED_PATH}")
        sys.exit(1)
    upload_url = response.get("upload_urls", {}).get(POLISHED_ID, {}).get("upload_url")
    if not upload_url:
        print("missing-polished-upload-url")
        sys.exit(1)
    print(f"uploading {POLISHED_ID} bytes={POLISHED.stat().st_size}")
    put_file(upload_url, POLISHED)
    job_id = response["job_id"]
    while True:
        status = api_request("GET", f"/jobs/{job_id}")
        write_json(POLISHED_STATUS_PATH, status)
        state = status.get("job_state")
        result_status = status.get("result", {}).get("status")
        print(f"polished-import-status state={state} result={result_status}")
        if state == "stopped":
            return status
        time.sleep(30)


def download_publish_to(status: dict[str, Any], target: Path) -> None:
    url = status.get("result", {}).get("download_url")
    if not url:
        print("no-download-url")
        return
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--location", "-o", str(target), url],
        check=True,
    )
    print(f"downloaded {target}")


def main() -> None:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else "all"
        if command in {"all", "start"}:
            start_import()
        if command == "resume":
            upload_existing()
            status = poll_import()
            comps = status.get("result", {}).get("created_compositions", [])
            if not comps:
                print("no-created-composition")
                sys.exit(1)
            composition_id = comps[0]["id"]
            print(f"composition {composition_id}")
            publish_status = publish(composition_id)
            download_publish(publish_status)
            return
        if command == "resume-camera":
            upload_existing({CAMERA_ID})
            status = poll_import()
            comps = status.get("result", {}).get("created_compositions", [])
            if not comps:
                print("no-created-composition")
                sys.exit(1)
            composition_id = comps[0]["id"]
            print(f"composition {composition_id}")
            publish_status = publish(composition_id)
            download_publish(publish_status)
            return
        if command == "import-polished":
            status = import_polished()
            comps = status.get("result", {}).get("created_compositions", [])
            if not comps:
                print("no-polished-created-composition")
                sys.exit(1)
            composition_id = comps[0]["id"]
            print(f"polished-composition {composition_id}")
            publish_status = publish(composition_id)
            download_publish_to(publish_status, POLISHED_EXPORT_PATH)
            return
        if command in {"all", "poll"}:
            status = poll_import()
            comps = status.get("result", {}).get("created_compositions", [])
            if not comps:
                print("no-created-composition")
                sys.exit(1)
            composition_id = comps[0]["id"]
            print(f"composition {composition_id}")
            publish_status = publish(composition_id)
            download_publish(publish_status)
        elif command == "publish":
            composition_id = sys.argv[2]
            publish_status = publish(composition_id)
            download_publish(publish_status)
    except Exception as exc:
        print(f"delivery-error {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
