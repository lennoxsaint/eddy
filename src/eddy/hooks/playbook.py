"""Offline short-form hook corpus gate.

Supadata is a build-time/source-acquisition tool here, not a runtime dependency for every edit.
Once the corpus has at least 1,000 validated hooks, Eddy can use it offline for Shorts taste.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Iterable

REQUIRED_FIELDS = {
    "hook_id",
    "source_url",
    "source_type",
    "platform",
    "opening_3s_text",
    "first_3_second_rationale",
    "hook_pattern",
    "pattern_tags",
    "payoff_type",
    "proven_score",
    "score_signals",
    "provenance",
}


def package_playbook_path(filename: str = "short-form-hook-playbook.jsonl") -> Path:
    return Path(__file__).resolve().parents[1] / "references" / filename


def resolve_playbook_path(path: Path | str) -> Path:
    """Resolve a hook playbook path, falling back to Eddy's packaged baked corpus.

    GitHub-source installs may not leave the repository `docs/` directory beside the installed
    package. The public playbook is therefore also included as package data under `eddy/references/`.
    """

    candidate = Path(path).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return candidate
    if not candidate.is_absolute() and candidate.exists():
        return candidate
    packaged = package_playbook_path(candidate.name)
    if packaged.exists():
        return packaged
    return candidate


def _stable_id(source_url: str, opening: str) -> str:
    return hashlib.sha256(f"{source_url}\n{opening}".encode("utf-8")).hexdigest()[:16]


def _norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def _tokens(text: str) -> set[str]:
    stop = {
        "a", "an", "and", "are", "for", "from", "how", "in", "is", "it", "of", "on", "or", "that",
        "the", "this", "to", "with", "you", "your",
    }
    return {t for t in _norm_text(text).split() if len(t) > 2 and t not in stop}


def validate_hook_record(record: dict) -> tuple[bool, list[str]]:
    problems: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        problems.append(f"missing:{','.join(missing)}")
    opening = str(record.get("opening_3s_text", "")).strip()
    if len(opening.split()) < 3:
        problems.append("opening_too_short")
    try:
        score = float(record.get("proven_score", -1))
    except (TypeError, ValueError):
        score = -1
    if score < 0.65:
        problems.append("score_below_threshold")
    if not str(record.get("source_url", "")).startswith(("http://", "https://")):
        problems.append("source_url_not_public")
    if not isinstance(record.get("provenance"), dict):
        problems.append("provenance_not_object")
    return not problems, problems


def load_playbook(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            rec = {"hook_id": f"invalid-line-{line_no}", "_invalid_json": str(exc)}
        records.append(rec)
    return records


def dedupe_records(records: Iterable[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for rec in records:
        key = str(rec.get("hook_id") or _stable_id(str(rec.get("source_url", "")), str(rec.get("opening_3s_text", ""))))
        opening_key = f"opening:{_norm_text(str(rec.get('opening_3s_text', '')))}"
        source_key = f"source:{rec.get('source_url', '')}"
        if key in seen or opening_key in seen or source_key in seen:
            continue
        seen.update({key, opening_key, source_key})
        rec = {**rec, "hook_id": key}
        out.append(rec)
    return out


def playbook_status(path: Path, min_records: int = 1000) -> dict:
    path = resolve_playbook_path(path)
    records = dedupe_records(load_playbook(path))
    valid: list[dict] = []
    invalid: list[dict] = []
    for rec in records:
        ok, problems = validate_hook_record(rec)
        (valid if ok else invalid).append({"hook_id": rec.get("hook_id"), "problems": problems} if not ok else rec)
    return {
        "path": str(path),
        "exists": Path(path).exists(),
        "raw_count": len(load_playbook(path)),
        "deduped_count": len(records),
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "required_count": min_records,
        "ready": len(valid) >= min_records,
        "blocker": None if len(valid) >= min_records else "short_form_hook_playbook_below_1000_valid_hooks",
        "provenance_sources": sorted(
            {
                str(rec.get("provenance", {}).get("source", "unknown"))
                for rec in valid
                if isinstance(rec.get("provenance"), dict)
            }
        ),
        "invalid_sample": invalid[:10],
    }


def require_hook_playbook(path: Path, min_records: int = 1000) -> dict:
    status = playbook_status(resolve_playbook_path(path), min_records=min_records)
    if not status["ready"]:
        raise RuntimeError(
            f"{status['blocker']}: {status['valid_count']}/{status['required_count']} valid hooks at {status['path']}"
        )
    return status


def build_record_from_supadata(source_url: str, metadata: dict, transcript: dict, extract: dict) -> dict:
    text = ""
    if isinstance(transcript.get("content"), str):
        text = transcript["content"]
    elif isinstance(transcript.get("transcript"), str):
        text = transcript["transcript"]
    else:
        chunks = transcript.get("chunks") or transcript.get("segments") or []
        text = " ".join(str(c.get("text", "")) for c in chunks[:4])
    opening = " ".join(text.split()[:18])
    pattern = str(extract.get("hook_pattern") or extract.get("summary") or "curiosity-proof").strip()[:120]
    return {
        "hook_id": _stable_id(source_url, opening),
        "source_url": source_url,
        "source_id": metadata.get("id") or metadata.get("video_id") or "",
        "source_type": "short_form_transcript",
        "platform": metadata.get("platform") or "youtube",
        "title": metadata.get("title", ""),
        "author": metadata.get("author") or metadata.get("channel", ""),
        "stats": metadata.get("stats") or {},
        "opening_3s_text": opening,
        "first_3_second_rationale": "Opening words extracted from the public transcript returned by Supadata.",
        "hook_pattern": pattern,
        "pattern_tags": sorted(_tokens(pattern) | _tokens(opening))[:12],
        "payoff_type": extract.get("payoff_type") or "closed-loop",
        "transcript_excerpt": text[:1200],
        "proven_score": float(extract.get("proven_score") or 0.65),
        "score_signals": {"supadata_extract_score": extract.get("proven_score"), "has_transcript": bool(text)},
        "provenance": {"source": "supadata", "metadata": bool(metadata), "transcript": bool(transcript), "extract": bool(extract)},
    }


def build_from_supadata(urls: list[str], out_path: Path, api_key: str | None = None) -> dict:
    """Fetch Supadata metadata/transcript/extract for a supplied URL list.

    Public URL discovery is deliberately out of scope. The caller provides public short-form URLs;
    Eddy validates and bakes the resulting playbook for offline use.
    """

    import httpx

    key = api_key or os.getenv("SUPADATA_API_KEY")
    if not key:
        raise RuntimeError("SUPADATA_API_KEY is required to build the hook playbook")
    base = "https://api.supadata.ai/v1"
    headers = {"x-api-key": key}
    records: list[dict] = []
    with httpx.Client(headers=headers) as client:
        for url in urls:
            params = {"url": url}
            metadata = client.get(f"{base}/metadata", params=params, timeout=60).json()
            transcript = client.get(f"{base}/transcript", params=params, timeout=120).json()
            extract = client.post(
                f"{base}/extract",
                json={"url": url, "schema": {"hook_pattern": "string", "payoff_type": "string", "proven_score": "number"}},
                timeout=120,
            ).json()
            records.append(build_record_from_supadata(url, metadata, transcript, extract))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in dedupe_records(records)) + "\n")
    return playbook_status(out_path)


DEFAULT_YOUTUBE_METADATA_QUERIES = [
    "#shorts business advice",
    "#shorts entrepreneur tips",
    "#shorts marketing tips",
    "#shorts content creation tips",
    "#shorts youtube growth",
    "#shorts creator economy",
    "#shorts ai tools",
    "#shorts productivity tips",
    "#shorts sales tips",
    "#shorts copywriting tips",
    "#shorts startup advice",
    "#shorts career advice",
    "#shorts finance tips",
    "#shorts investing tips",
    "#shorts psychology facts",
    "#shorts science facts",
    "#shorts coding tips",
    "#shorts design tips",
    "#shorts health tips",
    "#shorts fitness tips",
    "#shorts learning tips",
    "#shorts communication skills",
    "#shorts leadership tips",
    "#shorts negotiation tips",
    "#shorts personal branding",
    "#shorts social media tips",
    "#shorts email marketing",
    "#shorts side hustle tips",
    "#shorts small business tips",
    "#shorts mindset tips",
    "#shorts mistakes to avoid",
    "#shorts hidden truth",
    "#shorts nobody tells you",
    "#shorts do this instead",
    "#shorts before you start",
    "#shorts stop doing this",
    "#shorts how to get clients",
    "#shorts grow your audience",
    "#shorts make money online",
    "#shorts lessons learned",
    "#shorts things i wish i knew",
    "#shorts unpopular opinion",
    "#shorts common mistakes",
    "#shorts beginner mistakes",
    "#shorts creator mistakes",
    "#shorts marketing mistakes",
    "#shorts business mistakes",
    "#shorts sales mistakes",
    "#shorts life advice",
    "#shorts money advice",
    "#shorts career mistakes",
    "#shorts productivity hacks",
    "#shorts ai productivity",
    "#shorts chatgpt tips",
    "#shorts coding mistakes",
    "#shorts web design tips",
    "#shorts ux design tips",
    "#shorts entrepreneurship lessons",
    "#shorts startup mistakes",
    "#shorts client acquisition",
    "#shorts personal finance",
    "#shorts wealth building",
    "#shorts mindset shift",
    "#shorts psychology trick",
    "#shorts communication mistake",
    "#shorts storytelling tips",
    "#shorts content strategy",
    "#shorts viral hooks",
    "#shorts hook formula",
    "#shorts audience growth",
    "#shorts linkedin tips",
    "#shorts twitter growth",
    "#shorts instagram growth",
    "#shorts tiktok growth",
    "#shorts solopreneur tips",
    "#shorts online business",
    "#shorts creator business",
    "#shorts digital products",
    "#shorts community building",
]


def _classify_pattern(title: str) -> tuple[str, str]:
    t = _norm_text(title)
    if re.search(r"\b\d+\b", t):
        return "numbered-list", "ranked tips payoff"
    if t.startswith("how to ") or " how to " in f" {t} ":
        return "how-to promise", "step-by-step payoff"
    if any(w in t for w in ("mistake", "wrong", "avoid", "stop", "never")):
        return "mistake warning", "correction payoff"
    if any(w in t for w in ("secret", "truth", "hidden", "nobody tells")):
        return "truth reveal", "reveal payoff"
    if "?" in title:
        return "question gap", "answer payoff"
    if any(w in t for w in ("best", "worst", "actually", "surprising")):
        return "contrast claim", "verdict payoff"
    return "clear promise", "closed-loop payoff"


def _score_metadata_hook(view_count: int | None, rank: int, duration: float | None) -> float:
    views = max(int(view_count or 0), 0)
    view_signal = min(math.log10(views + 10) / 7.0, 1.0)
    rank_signal = max(0.0, 1.0 - ((rank - 1) / 100.0))
    duration_signal = 0.05 if duration and 8 <= duration <= 45 else 0.0
    return round(min(1.0, 0.65 + 0.24 * view_signal + 0.06 * rank_signal + duration_signal), 3)


def build_record_from_youtube_metadata(item: dict, query: str, rank: int, extracted_at: str) -> dict | None:
    title = re.sub(r"\s+#\\w+", "", str(item.get("title") or "")).strip()
    title = re.sub(r"\s+", " ", title)
    duration = item.get("duration")
    if not title or len(title.split()) < 3:
        return None
    if duration is None or float(duration) < 5 or float(duration) > 75:
        return None
    source_url = item.get("webpage_url") or item.get("url") or ""
    if not str(source_url).startswith("http"):
        return None
    pattern, payoff = _classify_pattern(title)
    return {
        "hook_id": _stable_id(str(source_url), title),
        "source_url": source_url,
        "source_id": item.get("id", ""),
        "platform": "youtube",
        "source_type": "short_form_metadata",
        "title": title,
        "author": item.get("channel") or item.get("uploader") or "",
        "stats": {
            "view_count": item.get("view_count"),
            "duration_s": duration,
            "query": query,
            "query_rank": rank,
        },
        "opening_3s_text": title,
        "first_3_second_rationale": "Public title metadata used as a title-derived hook surrogate; no transcript text is stored.",
        "hook_pattern": pattern,
        "pattern_tags": sorted(_tokens(pattern) | _tokens(title))[:12],
        "payoff_type": payoff,
        "transcript_span": None,
        "proven_score": _score_metadata_hook(item.get("view_count"), rank, float(duration)),
        "score_signals": {
            "view_count": item.get("view_count"),
            "query_rank": rank,
            "duration_s": duration,
            "title_pattern": pattern,
        },
        "provenance": {
            "source": "yt-dlp-youtube-metadata",
            "query": query,
            "extracted_at": extracted_at,
            "title_as_opening_surrogate": True,
            "no_video_download": True,
            "no_transcript_dump": True,
        },
    }


def build_from_youtube_metadata(
    out_path: Path,
    *,
    queries: list[str] | None = None,
    target_records: int = 1000,
    per_query: int = 80,
    min_records: int = 1000,
) -> dict:
    queries = queries or DEFAULT_YOUTUBE_METADATA_QUERIES
    extracted_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    records: list[dict] = []
    errors: list[dict] = []
    for query in queries:
        if len(dedupe_records(records)) >= target_records:
            break
        cmd = [
            "yt-dlp",
            "--no-update",
            "--ignore-errors",
            "--dump-json",
            "--flat-playlist",
            f"ytsearch{per_query}:{query}",
        ]
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode not in (0, 1):
            errors.append({"query": query, "returncode": proc.returncode, "stderr": proc.stderr[-500:]})
        rank = 0
        for line in proc.stdout.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            rank += 1
            rec = build_record_from_youtube_metadata(item, query, rank, extracted_at)
            if rec:
                records.append(rec)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    baked = dedupe_records(records)[:target_records]
    out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in baked) + "\n")
    status = playbook_status(out_path, min_records=min_records)
    status["builder"] = "youtube-metadata"
    status["queries"] = queries
    status["errors"] = errors[:10]
    return status


def hook_similarity(candidate_hook: str, records: Iterable[dict], sample_size: int = 250) -> float:
    tokens = _tokens(candidate_hook)
    if not tokens:
        return 0.0
    best = 0.0
    for rec in list(records)[:sample_size]:
        other = _tokens(str(rec.get("opening_3s_text", ""))) | _tokens(str(rec.get("hook_pattern", "")))
        if not other:
            continue
        best = max(best, len(tokens & other) / len(tokens | other))
    return round(best, 3)


def score_candidate_hook(candidate_hook: str, records: Iterable[dict]) -> dict:
    words = _norm_text(candidate_hook).split()
    first3_strength = 0.0
    if len(words) >= 4:
        first3_strength += 0.35
    if any(w in _norm_text(candidate_hook) for w in ("secret", "truth", "wrong", "stop", "never", "how", "why")):
        first3_strength += 0.25
    if re.search(r"\d", candidate_hook):
        first3_strength += 0.15
    similarity = hook_similarity(candidate_hook, records)
    score = min(1.0, first3_strength + (0.35 * similarity))
    return {
        "hook_score": round(score, 3),
        "first_3s_strength": round(first3_strength, 3),
        "playbook_similarity": similarity,
        "pass": score >= 0.45,
    }
