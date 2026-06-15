"""v0.7: opt-in anonymized failure beacon. OFF by default; sends only anonymized data, never PII."""

from eddy.beacon import beacon_payload, send_failure_beacon
from eddy.config import load_config
from eddy.media.ffmpeg import FfmpegError


def test_payload_is_anonymized_only():
    p = beacon_payload(FfmpegError("/Users/lennox/footage/secret.mp4 failed at frame 12"), stage="render")
    assert set(p) == {"eddy_version", "platform", "python", "ffmpeg", "stage", "error_class"}
    assert p["error_class"] == "FfmpegError" and p["stage"] == "render"
    # the error MESSAGE (which had a path) must not appear anywhere
    blob = " ".join(str(v) for v in p.values())
    assert "secret.mp4" not in blob and "/Users/" not in blob


def test_beacon_noop_when_disabled():
    cfg = load_config()
    cfg.telemetry.enabled = False
    assert send_failure_beacon(ValueError("x"), "run", cfg=cfg) is None


def test_beacon_noop_when_no_endpoint():
    cfg = load_config()
    cfg.telemetry.enabled = True
    cfg.telemetry.endpoint = ""
    assert send_failure_beacon(ValueError("x"), "run", cfg=cfg) is None


def test_beacon_posts_anonymized_when_opted_in(monkeypatch):
    cfg = load_config()
    cfg.telemetry.enabled = True
    cfg.telemetry.endpoint = "https://example.test/beacon"
    sent = {}

    import httpx

    monkeypatch.setattr(httpx, "post", lambda url, json=None, timeout=None: sent.update({"url": url, "json": json}))
    payload = send_failure_beacon(FfmpegError("boom at /home/bob/x.mp4"), "render", cfg=cfg)
    assert payload is not None and sent["url"] == "https://example.test/beacon"
    assert sent["json"]["error_class"] == "FfmpegError"
    assert "/home/" not in " ".join(str(v) for v in sent["json"].values())
