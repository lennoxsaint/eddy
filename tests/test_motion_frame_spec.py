from eddy.motion import frame_spec


def test_frame_md_precedence_beats_design_files(tmp_path):
    (tmp_path / "DESIGN.md").write_text("old")
    (tmp_path / "design.md").write_text("middle")
    frame = tmp_path / "frame.md"
    frame.write_text("---\naccent_primary: \"#37FF8B\"\n---\n# Frame\n")

    assert frame_spec.find_frame_spec(tmp_path) == frame
    assert frame_spec.parse_frontmatter(frame)["accent_primary"] == "#37FF8B"


def test_write_threadify_frame_contains_no_blur_rule(tmp_path):
    frame = frame_spec.write_threadify_proof_frame(tmp_path)
    tokens = frame_spec.parse_frontmatter(frame)

    assert tokens["frame_name"] == "Threadify Proof Frame"
    assert "#37FF8B" == tokens["accent_primary"]
    assert "blurred private data" in tokens["forbidden"]


def test_storyboard_primitives_and_html_are_written(tmp_path):
    frames = [{"time": "0:00", "title": "Proof Opens", "visual": "Receipt rail wakes up"}]

    md = frame_spec.write_storyboard(tmp_path, frames)
    html = frame_spec.write_storyboard_html(tmp_path, frames)

    assert "Proof Opens" in md.read_text()
    assert "Proof Opens" in html.read_text()
    assert "SAFE" in html.read_text()


def test_hyperframes_cache_and_selected_copy(tmp_path):
    hf = tmp_path / "hyperframes"
    (hf / "skills" / "motion-graphics").mkdir(parents=True)
    (hf / "skills" / "motion-graphics" / "SKILL.md").write_text("motion")
    (hf / "registry" / "components" / "caption-highlight").mkdir(parents=True)
    (hf / "registry" / "components" / "caption-highlight" / "index.tsx").write_text("caption")

    cache = tmp_path / "cache"
    index = frame_spec.write_hyperframes_cache(hf, cache)
    manifest = frame_spec.copy_hyperframes_references(hf, tmp_path / "vendor")

    assert index["asset_count"] == 2
    assert (cache / "hyperframes-pin.json").exists()
    assert any(item.get("status") == "copied" for item in manifest["copied"])
