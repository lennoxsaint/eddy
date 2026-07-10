"""The machine-readable public product contract for Eddy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EddyContract:
    product_name: str = "Eddy"
    primary_longs: int = 1
    alternate_longs: int = 2
    shared_body: bool = True
    shorts_range: tuple[int, int] = (3, 5)
    packaging_enabled: bool = False
    max_repair_attempts: int = 3
    red_attempt_destination: str = "quarantine"
    red_attempt_is_final: bool = False
    no_review_dogfoods_required: int = 5


def canonical_contract() -> EddyContract:
    """Return the immutable v3.0 owner-approved contract."""

    return EddyContract()

