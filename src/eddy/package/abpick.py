"""v0.8: A/B title (+ thumbnail) pick from a reusable decision template.

Packaging emits ~10 title candidates; a creator running an A/B test wants TWO strong but
*divergent* options, picked the same way every run. The rubric below IS that reusable decision
template — a deterministic, reproducible scorer (no model call, no per-run drift). It scores YouTube
title-craft signals we can measure from text, then picks A = top score and B = the highest-scoring
candidate that diverges enough from A to make the test meaningful (testing two near-identical titles
learns nothing). Thumbnails can't be scored without vision, so we pair distinct generated files
honestly and say so."""

from __future__ import annotations

import json
import re
from pathlib import Path

# The reusable decision template. Tweak weights/ranges here and every run inherits it.
TITLE_AB_RUBRIC: dict = {
    "ideal_chars": (40, 60),     # YouTube title sweet spot before truncation
    "hard_max_chars": 70,
    "min_divergence": 0.5,       # 1 - jaccard(tokens) between A and B must be >= this
    "power_words": (
        "secret", "mistake", "stop", "never", "always", "why", "how", "proven", "fast",
        "easy", "truth", "best", "worst", "nobody", "everyone", "actually", "real",
        "simple", "hidden", "wrong", "right", "first", "free", "now",
    ),
    "weights": {
        "length_fit": 3.0,       # within ideal_chars
        "has_number": 2.0,       # specificity / listicle pull
        "curiosity": 2.0,        # question or curiosity gap
        "power_word": 1.5,       # per power word (capped)
        "front_loaded": 1.0,     # a strong word in the first 3 tokens
        "clean": 1.0,            # not shouty / not over-punctuated
    },
}

_TOKEN = re.compile(r"[a-z0-9']+")


def _tokens(title: str) -> set[str]:
    return set(_TOKEN.findall(title.lower()))


def _divergence(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0
    return 1.0 - len(ta & tb) / len(ta | tb)


def score_title(title: str, rubric: dict = TITLE_AB_RUBRIC) -> dict:
    """Deterministic score + the signals that produced it (auditable, no model)."""
    w = rubric["weights"]
    lo, hi = rubric["ideal_chars"]
    n = len(title)
    toks = _TOKEN.findall(title.lower())
    signals: dict = {}
    score = 0.0

    if lo <= n <= hi:
        signals["length_fit"] = True
        score += w["length_fit"]
    elif n <= rubric["hard_max_chars"]:
        signals["length_fit"] = "near"
        score += w["length_fit"] * 0.5

    if any(c.isdigit() for c in title):
        signals["has_number"] = True
        score += w["has_number"]

    if "?" in title or title.lower().split(" ", 1)[0] in ("why", "how", "what", "when", "who"):
        signals["curiosity"] = True
        score += w["curiosity"]

    power = [t for t in toks if t in rubric["power_words"]]
    if power:
        signals["power_words"] = power
        score += min(len(power), 2) * w["power_word"]

    if toks[:3] and any(t in rubric["power_words"] for t in toks[:3]):
        signals["front_loaded"] = True
        score += w["front_loaded"]

    letters = [c for c in title if c.isalpha()]
    shouty = letters and sum(c.isupper() for c in letters) / len(letters) > 0.6
    over_punct = title.count("!") + title.count("?") > 2
    if not shouty and not over_punct:
        signals["clean"] = True
        score += w["clean"]

    return {"title": title, "score": round(score, 2), "chars": n, "signals": signals}


def pick_ab(titles: list[dict], rubric: dict = TITLE_AB_RUBRIC) -> dict:
    """Rank candidates; A = best, B = best candidate that diverges >= min_divergence from A.
    `titles` are dicts with a 'title' key (packaging's title candidates)."""
    # secondary key on title text so score ties break deterministically regardless of the model's
    # (nondeterministic) candidate ordering — keeps the whole pick reproducible run-to-run.
    scored = sorted(
        (score_title(t["title"], rubric) for t in titles if t.get("title")),
        key=lambda s: (-s["score"], s["title"]),
    )
    if not scored:
        return {"a": None, "b": None, "ranked": [], "note": "no title candidates"}
    a = scored[0]
    b = None
    for cand in scored[1:]:
        if _divergence(a["title"], cand["title"]) >= rubric["min_divergence"]:
            b = cand
            break
    note = ""
    if b is None and len(scored) > 1:
        b = scored[1]  # nothing diverged enough — fall back to 2nd best, but flag the weak test
        note = "B is the 2nd-best title but overlaps A; the A/B test may be weak"
    return {"a": a, "b": b, "ranked": scored, "divergence": round(_divergence(a["title"], b["title"]), 2) if b else None, "note": note}


def pick_thumbnail_ab(thumb_dir: Path) -> dict:
    """Pair two distinct generated thumbnail files for an A/B test. No visual scoring (no vision
    model) — this is an honest pairing, not a quality judgement."""
    thumb_dir = Path(thumb_dir)
    pngs = sorted(p for p in thumb_dir.glob("*.png") if not p.name.startswith("refs"))
    if len(pngs) < 2:
        return {"a": None, "b": None, "note": f"need >=2 generated thumbnails, found {len(pngs)}"}
    return {"a": pngs[0].name, "b": pngs[1].name,
            "note": "thumbnails paired by file order; eddy has no vision model to rank them visually"}


def build_ab_pick(run_dir: Path, titles: list[dict] | None = None) -> Path:
    """Write final/ab-pick.json + final/AB-TEST.md. `titles` may be passed during packaging; else it
    reads the persisted final/titles.json (so `eddy pick <run_dir>` works standalone)."""
    final_dir = Path(run_dir) / "final"
    if titles is None:
        tj = final_dir / "titles.json"
        titles = json.loads(tj.read_text()) if tj.exists() else []

    title_ab = pick_ab(titles)
    thumb_ab = pick_thumbnail_ab(final_dir / "thumbnails")
    result = {"title": title_ab, "thumbnail": thumb_ab, "rubric": "TITLE_AB_RUBRIC"}
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "ab-pick.json").write_text(json.dumps(result, indent=2))

    a, b = title_ab["a"], title_ab["b"]
    lines = ["# A/B test picks", "", "## Titles (deterministic rubric)"]
    if a:
        lines.append(f"- **A** (score {a['score']}): {a['title']}")
    if b:
        lines.append(f"- **B** (score {b['score']}): {b['title']}")
    if title_ab.get("divergence") is not None:
        lines.append(f"- divergence A↔B: {title_ab['divergence']} (1.0 = no shared words)")
    if title_ab.get("note"):
        lines.append(f"- ⚠ {title_ab['note']}")
    lines += ["", "## Thumbnails"]
    if thumb_ab["a"]:
        lines.append(f"- **A**: {thumb_ab['a']}")
        lines.append(f"- **B**: {thumb_ab['b']}")
    lines.append(f"- {thumb_ab['note']}")
    (final_dir / "AB-TEST.md").write_text("\n".join(lines) + "\n")
    return final_dir / "ab-pick.json"
