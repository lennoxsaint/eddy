"""v0.8: content-format profiles — tutorials/lessons/longform raise the length ceiling so the loop
doesn't compress step-by-step content."""

from eddy.formats import resolve_format


def test_default_uses_configured_ceiling():
    assert resolve_format("default")["ceiling_minutes"] is None  # None = use the config 14-min ceiling


def test_tutorial_and_longform_raise_ceiling():
    for name in ("tutorial", "lesson", "longform", "podcast"):
        assert resolve_format(name)["ceiling_minutes"] == 600.0  # effectively no ceiling


def test_unknown_and_case_insensitive():
    assert resolve_format("TUTORIAL")["ceiling_minutes"] == 600.0
    assert resolve_format("nonsense")["ceiling_minutes"] is None   # falls back to default
    assert resolve_format("")["ceiling_minutes"] is None
