import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_motion_script():
    spec = importlib.util.spec_from_file_location(
        "motion_render",
        ROOT / "scripts" / "motion_render.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portrait_stat_uses_compact_skeuomorphic_panel() -> None:
    motion = load_motion_script()
    brief = {
        "width": 1080,
        "height": 1920,
        "duration": 2.0,
        "beats": [
            {
                "start": 0.0,
                "dur": 1.4,
                "layout": "stat",
                "value": "ANY MODEL",
                "label": "ONE CLICK",
            }
        ],
    }

    html = motion.build_custom_html(brief, None, None)

    assert "contextual-panel" in html
    assert ".stat { font-size:72px;" in html
    assert "windowbar" in html
    assert '<div class="stat stagger">ANY MODEL</div>' in html
    assert '<div class="sub stagger">ONE CLICK</div>' in html


def test_landscape_stat_uses_compact_type_instead_of_covering_the_screen() -> None:
    motion = load_motion_script()
    html = motion.build_custom_html(
        {"width": 1920, "height": 1080, "duration": 1.0, "beats": []},
        None,
        None,
    )

    assert ".stat { font-size:88px;" in html
    assert "font-size:300px" not in html
