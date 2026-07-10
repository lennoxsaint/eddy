import numpy as np

from eddy.motion_layout import resolve_motion_layout


def test_landscape_motion_chooses_a_quiet_region_and_avoids_pip() -> None:
    frame = np.full((1080, 1920, 3), 245, dtype=np.uint8)
    frame[120:930, :1100:4] = 20
    brief = {
        "width": 1920,
        "height": 1080,
        "beats": [{"id": "proof", "start": 1.0, "dur": 1.5, "layout": "stat"}],
    }

    resolved, proof = resolve_motion_layout(brief, [frame], portrait=False)

    beat = resolved["beats"][0]
    assert beat["placement"] in {"top-right", "middle-right"}
    assert beat["x"] >= 1100
    assert beat["y"] + beat["h"] <= 800
    assert proof["pass"] is True
    assert proof["contract"] == "contextual_skeuomorphic_v1"


def test_portrait_motion_stays_below_face_and_caption_band() -> None:
    frame = np.full((1920, 1080, 3), 210, dtype=np.uint8)
    brief = {
        "width": 1080,
        "height": 1920,
        "beats": [{"id": "hook", "start": 0.0, "dur": 1.4, "layout": "stat"}],
    }

    resolved, proof = resolve_motion_layout(brief, [frame], portrait=True)

    beat = resolved["beats"][0]
    assert beat["y"] >= 1300
    assert beat["y"] + beat["h"] <= 1860
    assert proof["beats"][0]["reserved_overlap_ratio"] == 0.0
    assert proof["pass"] is True
