"""v0.5: golden editorial suite — reproducibility anchor pinned to the LOCAL qwen model.

A cloud model can't be frozen, so the golden gate pins the local model (config editorial=local).
It is OPT-IN (EDDY_GOLDEN=1) and slow (real 27B inference), and skips when the pinned model isn't
available — so the fast suite is unaffected. It asserts a TOLERANCE property (the pinned model
returns schema-valid editorial output that builds a valid EditDecisions), not an exact transcript,
since temperature makes exact output non-reproducible. v1.0 promotes this to a required GA gate.
"""

import os
from pathlib import Path

import pytest

from eddy.config import load_config
from eddy.edit.cutplan import DECISIONS_SCHEMA
from eddy.edit.schema import EditDecisions
from eddy.loop.controller import _editorial_model_id
from eddy.providers.base import get_editorial_provider

PROMPTS = Path(__file__).resolve().parents[1] / "src" / "eddy" / "prompts"
pytestmark = pytest.mark.skipif(not os.environ.get("EDDY_GOLDEN"), reason="opt-in golden suite (slow; needs the pinned local model)")


def _pinned_model_available(cfg) -> bool:
    pin = _editorial_model_id(cfg)
    if pin["provider"] != "ollama":
        return False
    try:
        import httpx

        tags = httpx.get(cfg.provider.ollama.base_url.replace("/v1", "") + "/api/tags", timeout=3).json()
        return any(m.get("name") == pin["model"] for m in tags.get("models", []))
    except Exception:
        return False


def test_pinned_model_produces_valid_editorial_output():
    cfg = load_config()
    cfg.provider.editorial = "local"  # pin to the local model (the freezable reproducibility anchor)
    if not _pinned_model_available(cfg):
        pytest.skip(f"pinned model {_editorial_model_id(cfg)['model']} not available in ollama")

    provider = get_editorial_provider(cfg)
    prompt = (PROMPTS / "cutplan.md").read_text()
    transcript = (
        "[0.00-3.00] So the key idea here is that systems beat goals.\n"
        "[3.00-6.00] Um, like, you know, goals are about, uh, the result you want.\n"
        "[6.00-9.00] Systems are about the daily process that gets you there.\n"
        "[9.00-12.00] So the key idea here is that systems beat goals."  # a deliberate retake of line 1
    )
    content = (
        f"{prompt}\n\nTARGET RUNTIME: 8 seconds\n\n"
        'BEAT MAP:\n[{"label":"intro","start_s":0,"end_s":12,"summary":"systems vs goals"}]\n\n'
        f"TRANSCRIPT:\n{transcript}"
    )
    raw = provider.complete([{"role": "user", "content": content}], schema=DECISIONS_SCHEMA, max_tokens=4096)

    # TOLERANCE: schema-valid editorial output that builds a valid EditDecisions with the
    # expected structure (lists for cuts/retakes/protected_moments). Exact picks vary by sampling.
    decisions = EditDecisions.model_validate({**raw, "target_runtime_seconds": 8})
    assert isinstance(decisions.cuts, list)
    assert isinstance(decisions.retakes, list)
    assert isinstance(decisions.protected_moments, list)
    # the model was given an obvious retake + filler; a healthy editorial pass proposes SOME removal
    assert decisions.cuts or decisions.retakes, "pinned model proposed no cuts or retakes on filler-heavy input"
