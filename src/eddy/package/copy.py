"""Packaging copy: titles (quote-grounded), deterministic chapters, description."""

from __future__ import annotations

import json
from pathlib import Path

from eddy.edit.compiler import src_to_out
from eddy.edit.schema import EditDecisions, Edl
from eddy.loop.receipts import Receipts

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

TITLES_SCHEMA = {
    "type": "object",
    "required": ["titles"],
    "properties": {
        "titles": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "grounding_quote"],
                "properties": {
                    "title": {"type": "string"},
                    "grounding_quote": {"type": "string"},
                    "mechanism": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            },
        }
    },
}

DESCRIPTION_SCHEMA = {
    "type": "object",
    "required": ["description"],
    "properties": {"description": {"type": "string"}},
}

LABEL_SCHEMA = {
    "type": "object",
    "required": ["labels"],
    "properties": {"labels": {"type": "array", "items": {"type": "string"}}},
}


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapters(edl: Edl, decisions: EditDecisions, provider, receipts: Receipts) -> list[dict]:
    """Deterministic timestamps: beat boundaries mapped to the OUTPUT timeline.
    The model writes labels only."""
    beats = decisions.x_eddy.beats
    if not beats:
        return []

    chaps: list[dict] = []
    for b in beats:
        t = src_to_out(edl, b.get("start_s", 0.0))  # speed-aware shared remap
        if t is None:
            continue
        if chaps and t - chaps[-1]["out_s"] < 10:
            continue
        chaps.append({"out_s": round(t, 1), "beat": b.get("label", ""), "summary": b.get("summary", "")})
    if chaps:
        chaps[0]["out_s"] = 0.0

    try:
        result = provider.complete(
            [
                {
                    "role": "user",
                    "content": (
                        "Write a 2-5 word YouTube chapter label for each beat below, viewer-facing, "
                        "no colons, no numbering. Return ONLY JSON {\"labels\": [...]}, one label per "
                        f"beat in order.\n\nBEATS:\n{json.dumps([{k: c[k] for k in ('beat', 'summary')} for c in chaps], indent=1)}"
                    ),
                }
            ],
            schema=LABEL_SCHEMA,
            max_tokens=512,
        )
        labels = result["labels"]
    except Exception as e:
        receipts.log("chapter_labels_fallback", error=str(e)[:200])
        labels = [c["beat"].replace("_", " ").title() for c in chaps]

    for c, label in zip(chaps, labels):
        c["label"] = label.strip()
    for c in chaps:
        c.setdefault("label", c["beat"].title())
    return chaps


def chapters_block(chaps: list[dict]) -> str:
    return "\n".join(f"{_fmt_ts(c['out_s'])} {c['label']}" for c in chaps)


def _no_em_dashes(text: str) -> str:
    return text.replace("\u2014", " - ").replace("\u2013", "-").replace("  ", " ")


def titles(kept_phrases: list[dict], provider, receipts: Receipts) -> list[dict]:
    prompt = (PROMPTS / "titles.md").read_text()
    transcript = "\n".join(p["text"] for p in kept_phrases)
    result = provider.complete(
        [{"role": "user", "content": f"{prompt}\n\nFINAL CUT TRANSCRIPT:\n{transcript}"}],
        schema=TITLES_SCHEMA,
        max_tokens=2048,
    )
    receipts.log("titles", count=len(result["titles"]))
    cleaned = result["titles"][:10]
    for item in cleaned:
        item["title"] = _no_em_dashes(item["title"])
    return cleaned


def description(kept_phrases: list[dict], chaps: list[dict], provider, receipts: Receipts, cta: str = "") -> str:
    prompt = (PROMPTS / "description.md").read_text()
    transcript = "\n".join(p["text"] for p in kept_phrases)
    block = chapters_block(chaps)
    content = f"{prompt}\n\nCHAPTERS BLOCK:\n{block}\n\n"
    if cta:
        content += f"CTA LINE (verbatim, after chapters):\n{cta}\n\n"
    content += f"FINAL CUT TRANSCRIPT:\n{transcript}"
    result = provider.complete([{"role": "user", "content": content}], schema=DESCRIPTION_SCHEMA, max_tokens=2048)
    desc = _no_em_dashes(result["description"])
    if block and block not in desc:
        desc = desc.rstrip() + "\n\nChapters:\n" + block
    receipts.log("description", chars=len(desc))
    return desc


def write_copy_artifacts(
    final_dir: Path, title_list: list[dict], desc: str, chaps: list[dict]
) -> None:
    final_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Title candidates\n"]
    for i, t in enumerate(title_list, 1):
        lines.append(f"{i}. **{t['title']}**")
        lines.append(f"   - mechanism: {t.get('mechanism', '')}")
        lines.append(f"   - grounded by: \"{t['grounding_quote'][:140]}\"")
        lines.append(f"   - {t.get('rationale', '')}")
    (final_dir / "titles.md").write_text("\n".join(lines) + "\n")
    (final_dir / "description.md").write_text(desc + "\n")
    (final_dir / "chapters.txt").write_text(chapters_block(chaps) + "\n")
