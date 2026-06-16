"""Thumbnail candidates: sharp face frames -> Gemini + OpenAI image APIs.

The ONLY paid path in Eddy. Every call cost-logged; missing keys degrade to a
skip receipt, never a crash."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import httpx

from eddy.config import EddyConfig
from eddy.loop.receipts import Receipts


def _write_placeholder_thumbnail(out_dir: Path, title_hint: str) -> Path | None:
    """A local, offline title-card the creator can use as a STARTING POINT — not a generated
    thumbnail (it's clearly labeled and excluded from the A/B pairing). Pure PIL, no network, so
    `--local-only` runs still leave a frame in the kit instead of an empty thumbnails folder."""
    try:
        from PIL import Image, ImageDraw

        from eddy.render.captions import load_font

        w, h = 1280, 720
        img = Image.new("RGB", (w, h), (16, 22, 38))  # brand navy
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 24, h], fill=(245, 184, 54))  # gold accent bar
        title_font, small = load_font(72), load_font(26)
        lines: list[str] = []
        cur = ""
        for word in (title_hint or "Your title here").split():
            if len(cur) + len(word) + 1 > 20:
                lines.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            lines.append(cur)
        y = 120
        for ln in lines[:5]:
            d.text((70, y), ln, font=title_font, fill=(238, 238, 238))
            y += 90
        d.text((70, h - 64), "PLACEHOLDER - generated offline, replace before publishing",
               font=small, fill=(139, 144, 155))
        path = out_dir / "placeholder.png"
        img.save(path)
        return path
    except Exception:
        return None  # never let a nicety crash packaging


def _thumb_prompt(title_hint: str) -> str:
    return (
        "Create a YouTube thumbnail (16:9, 1280x720) featuring this exact person from the "
        "reference photo - preserve their real face, hair, and skin tone faithfully (no beautifying, "
        "no face swap). Style: high-contrast creator thumbnail, single dominant subject, expressive "
        "face large on the right third, bold 3-5 word text on the left that complements (not repeats) "
        f'the title "{title_hint}". Clean dark background with one accent color, readable at phone size, '
        "no watermarks, no channel logos, no fake UI."
    )


def generate_gemini(ref_frame: Path, title_hint: str, out_dir: Path, cfg: EddyConfig, receipts: Receipts, n: int) -> list[Path]:
    key = os.environ.get(cfg.thumbnails.gemini_key_env) or os.environ.get("GOOGLE_API_KEY")
    if not key:
        receipts.log("thumbnails_skipped", provider="gemini", reason="no API key")
        return []
    out: list[Path] = []
    img_b64 = base64.b64encode(ref_frame.read_bytes()).decode()
    body = {
        "contents": [
            {
                "parts": [
                    {"text": _thumb_prompt(title_hint)},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                ]
            }
        ],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.thumbnails.gemini_model}:generateContent"
    )
    for i in range(n):
        try:
            r = httpx.post(url, params={"key": key}, json=body, timeout=120)
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            data = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
            path = out_dir / f"gemini-{i + 1}.png"
            path.write_bytes(base64.b64decode(data))
            out.append(path)
            receipts.log("thumbnail", provider="gemini", path=str(path), est_cost_usd=0.04)
        except Exception as e:
            receipts.log("thumbnail_failed", provider="gemini", error=str(e)[:300])
    return out


def generate_openai(ref_frame: Path, title_hint: str, out_dir: Path, cfg: EddyConfig, receipts: Receipts, n: int) -> list[Path]:
    key = os.environ.get(cfg.thumbnails.openai_key_env)
    if not key:
        receipts.log("thumbnails_skipped", provider="openai", reason="no API key")
        return []
    out: list[Path] = []
    try:
        with ref_frame.open("rb") as f:
            r = httpx.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {key}"},
                data={
                    "model": "gpt-image-1",
                    "prompt": _thumb_prompt(title_hint),
                    "size": "1536x1024",
                    "n": str(n),
                },
                files={"image": ("ref.jpg", f, "image/jpeg")},
                timeout=300,
            )
        r.raise_for_status()
        for i, item in enumerate(r.json()["data"][:n]):
            path = out_dir / f"openai-{i + 1}.png"
            path.write_bytes(base64.b64decode(item["b64_json"]))
            out.append(path)
            receipts.log("thumbnail", provider="openai", path=str(path), est_cost_usd=0.07)
    except Exception as e:
        receipts.log("thumbnail_failed", provider="openai", error=str(e)[:300])
    return out


def generate_thumbnails(
    run_dir: Path, ref_frames: list[Path], title_hint: str, cfg: EddyConfig, receipts: Receipts
) -> list[Path]:
    from eddy.privacy import is_offline

    out_dir = Path(run_dir) / "final" / "thumbnails"
    out_dir.mkdir(parents=True, exist_ok=True)
    # thumbnails upload a real FACE frame to cloud image APIs. Skip unless: online, enabled,
    # explicit upload consent, and reference frames exist. Consent is opt-in so a person's
    # likeness is never sent automatically.
    if is_offline() or not cfg.thumbnails.enabled or not cfg.thumbnails.consent_to_upload or not ref_frames:
        if is_offline():
            reason = "offline (--local-only)"
        elif not cfg.thumbnails.consent_to_upload:
            reason = "no face-upload consent (set thumbnails.consent_to_upload=true to enable)"
        else:
            reason = "disabled or no reference frames"
        receipts.log("thumbnails_skipped", reason=reason)
        skip: dict = {"reason": reason}
        if is_offline():  # offline can't reach the image APIs — leave a local title-card to start from
            ph = _write_placeholder_thumbnail(out_dir, title_hint)
            if ph is not None:
                skip["placeholder"] = ph.name
                receipts.log("thumbnail_placeholder", path=str(ph))
        (out_dir / "thumbnails-skipped.json").write_text(json.dumps(skip))
        return []
    ref = ref_frames[0]
    for f in ref_frames:
        (out_dir / f"reference-{f.name}").write_bytes(f.read_bytes())
    n = cfg.thumbnails.candidates_per_provider
    results = generate_gemini(ref, title_hint, out_dir, cfg, receipts, n)
    results += generate_openai(ref, title_hint, out_dir, cfg, receipts, n)
    if not results:
        (out_dir / "thumbnails-skipped.json").write_text(
            json.dumps({"reason": "no provider produced an image; see receipts"})
        )
    return results
