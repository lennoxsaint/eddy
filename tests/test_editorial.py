import json
from pathlib import Path

from eddy.editorial import build_editorial_ledger, validate_editorial_review


def _word(word: str, start: float, end: float) -> dict:
    return {"word": word, "start": start, "end": end}


def test_editorial_ledger_finds_separated_repeat_and_long_gap(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    words = [
        _word("you", 0.0, 0.1),
        _word("point", 0.1, 0.2),
        _word("this", 0.2, 0.3),
        _word("exact", 0.3, 0.4),
        _word("same", 0.4, 0.5),
        _word("setup", 0.5, 0.6),
        _word("you", 4.0, 4.1),
        _word("point", 4.1, 4.2),
        _word("this", 4.2, 4.3),
        _word("exact", 4.3, 4.4),
        _word("same", 4.4, 4.5),
        _word("setup", 4.5, 4.6),
    ]
    transcript.write_text(json.dumps({"words": words}) + "\n")

    ledger = build_editorial_ledger(transcript)

    assert any(item["kind"] == "repeat" for item in ledger["candidates"])
    assert any(item["kind"] == "long_gap" for item in ledger["candidates"])
    assert ledger["chunks"]


def test_generic_sentence_scaffolding_is_not_a_repeat(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    tokens = [
        "Two,", "and", "this", "is", "the", "load", "bearing", "trick.",
        "And", "this", "is", "the", "big", "one.",
    ]
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    _word(token, index * 0.2, index * 0.2 + 0.1)
                    for index, token in enumerate(tokens)
                ]
            }
        )
        + "\n"
    )

    ledger = build_editorial_ledger(transcript)

    assert all(item["kind"] != "repeat" for item in ledger["candidates"])


def test_contentful_repeated_claim_still_blocks(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    tokens = [
        "The", "fix", "is", "the", "local", "proxy.",
        "The", "fix", "is", "the", "app", "points", "at", "the", "local", "proxy.",
    ]
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    _word(token, index * 0.2, index * 0.2 + 0.1)
                    for index, token in enumerate(tokens)
                ]
            }
        )
        + "\n"
    )

    ledger = build_editorial_ledger(transcript)

    assert any(item["kind"] == "repeat" for item in ledger["candidates"])


def test_editorial_review_must_cover_chunks_and_resolve_candidates(tmp_path: Path) -> None:
    ledger = {
        "chunks": [{"id": "chunk-1", "start": 0.0, "end": 60.0, "text": "text"}],
        "candidates": [
            {
                "id": "repeat-1",
                "kind": "repeat",
                "requires_resolution": True,
                "recommended_variant_id": "variant-b",
                "variants": [
                    {"id": "variant-a", "start": 0.0, "end": 1.0},
                    {"id": "variant-b", "start": 2.0, "end": 3.0},
                ],
            }
        ],
    }
    review = {
        "coverage": [[0.0, 60.0]],
        "resolutions": [
            {
                "candidate_id": "repeat-1",
                "action": "keep_last",
                "selected_variant_id": "variant-b",
                "reason": "last clean take",
            }
        ],
    }

    assert validate_editorial_review(ledger, review) == []
    assert "editorial_candidate_unresolved:repeat-1" in validate_editorial_review(
        ledger, {**review, "resolutions": []}
    )


def test_editorial_ledger_includes_audio_only_silence(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    _word("before", 0.0, 0.2),
                    _word("after", 0.3, 0.5),
                ]
            }
        )
        + "\n"
    )

    ledger = build_editorial_ledger(transcript, silence_spans=[[2.0, 4.5]])

    candidate = next(item for item in ledger["candidates"] if item["kind"] == "long_gap")
    assert candidate["source"] == "audio"
    assert candidate["duration"] == 2.5


def test_editorial_ledger_flags_reset_loop_and_unfinished_clause(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    words = [
        _word("Okay.", 0.0, 0.2),
        _word("So", 1.2, 1.4),
        _word("the", 1.4, 1.6),
        _word("fix...", 1.6, 1.8),
        _word("Okay.", 2.8, 3.0),
        _word("So", 4.0, 4.2),
        _word("I", 4.2, 4.4),
        _word("have", 4.4, 4.6),
        _word("a", 4.6, 4.8),
        _word("question.", 4.8, 5.0),
    ]
    transcript.write_text(json.dumps({"words": words}) + "\n")

    ledger = build_editorial_ledger(transcript)

    kinds = {item["kind"] for item in ledger["candidates"]}
    assert "reset_loop" in kinds
    assert "false_start" in kinds


def test_legitimate_so_led_sentences_do_not_create_reset_loop(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    words = [
        _word("So", 0.0, 0.1),
        _word("this", 0.1, 0.2),
        _word("protects", 0.2, 0.3),
        _word("privacy.", 0.3, 0.4),
        _word("So", 3.0, 3.1),
        _word("the", 3.1, 3.2),
        _word("model", 3.2, 3.3),
        _word("runs", 3.3, 3.4),
        _word("locally.", 3.4, 3.5),
    ]
    transcript.write_text(json.dumps({"words": words}) + "\n")

    ledger = build_editorial_ledger(transcript)

    assert all(item["kind"] != "reset_loop" for item in ledger["candidates"])


def test_ellipsis_continuation_is_not_a_false_start(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    tokens = [
        "What", "we", "do", "instead", "is...",
        "three", "separate", "pieces.",
        "So", "the", "newer", "Codex...",
        "only", "talks", "one", "wire", "format.",
    ]
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    _word(token, index * 0.2, index * 0.2 + 0.1)
                    for index, token in enumerate(tokens)
                ]
            }
        )
        + "\n"
    )

    ledger = build_editorial_ledger(transcript)

    assert all(
        item["kind"] not in {"false_start", "reset_loop"}
        for item in ledger["candidates"]
    )


def test_audio_and_transcript_gap_evidence_is_deduplicated(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        json.dumps(
            {
                "words": [
                    _word("before", 0.0, 0.2),
                    _word("after", 2.0, 2.2),
                ]
            }
        )
        + "\n"
    )

    ledger = build_editorial_ledger(transcript, silence_spans=[[0.25, 1.95]])

    gaps = [item for item in ledger["candidates"] if item["kind"] == "long_gap"]
    assert len(gaps) == 1
    assert gaps[0]["source"] == "audio+transcript"
