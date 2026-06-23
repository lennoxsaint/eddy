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
