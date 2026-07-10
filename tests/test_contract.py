from pathlib import Path

from eddy.contract import canonical_contract


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_contract_is_videos_only_with_three_ranked_longs() -> None:
    contract = canonical_contract()

    assert contract.product_name == "Eddy"
    assert contract.primary_longs == 1
    assert contract.alternate_longs == 2
    assert contract.shared_body is True
    assert contract.shorts_range == (3, 5)
    assert contract.packaging_enabled is False
    assert contract.no_review_dogfoods_required == 5


def test_red_attempts_are_quarantined_not_delivered() -> None:
    contract = canonical_contract()

    assert contract.max_repair_attempts == 3
    assert contract.red_attempt_destination == "quarantine"
    assert contract.red_attempt_is_final is False


def test_skill_declares_the_machine_readable_contract() -> None:
    skill = (ROOT / "SKILL.md").read_text()

    assert "one ranked primary long" in skill
    assert "two complete alternate-hook longs" in skill
    assert "videos only" in skill
    assert "Blocked Attempt" in skill
    assert "Effect-Survival Gate" in skill
    assert "five owner-approved dogfood runs" in skill
