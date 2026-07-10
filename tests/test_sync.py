from pathlib import Path

from eddy.sync import CANONICAL_SURFACES, build_manifest, check_projection


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_hashes_every_canonical_skill_surface() -> None:
    manifest = build_manifest(ROOT, canonical_commit="abc123")

    assert manifest["schema_version"] == "eddy-surface-manifest-v1"
    assert manifest["canonical_commit"] == "abc123"
    assert set(manifest["files"]) == set(CANONICAL_SURFACES)
    assert all(len(value) == 64 for value in manifest["files"].values())


def test_projection_check_reports_changed_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    projection = tmp_path / "projection"
    source.mkdir()
    projection.mkdir()
    (source / "SKILL.md").write_text("canonical\n")
    (projection / "SKILL.md").write_text("drifted\n")

    result = check_projection(source, projection, files=("SKILL.md",))

    assert result.ok is False
    assert result.changed == ("SKILL.md",)

