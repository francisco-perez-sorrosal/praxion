from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTER_PATH = REPO_ROOT / "codex" / "config" / "export-codex-skills.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_codex_skills", EXPORTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_skills_writes_wrapper_with_full_description(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / "skills"

    written = exporter.export_skills(REPO_ROOT, out_dir)

    assert written
    skill = out_dir / "ml-training" / "SKILL.md"
    assert skill in written
    text = skill.read_text(encoding="utf-8")
    assert "name: ml-training" in text
    assert "This is a Codex skill wrapper for Praxion." in text
    assert f"`{(REPO_ROOT / 'skills' / 'ml-training' / 'SKILL.md').resolve().as_posix()}`" in text
    description_line = next(line for line in text.splitlines() if line.startswith("description: "))
    description = description_line.split(": ", 1)[1]
    assert description.startswith("'")
    assert description.endswith("'")
    source_metadata, _ = exporter.parse_frontmatter_skill(
        REPO_ROOT / "skills" / "ml-training" / "SKILL.md"
    )
    source_description = source_metadata["description"]
    assert description[1:-1] == source_description


def test_export_skills_preserves_all_canonical_descriptions(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / "skills"

    written = exporter.export_skills(REPO_ROOT, out_dir)

    for skill_path in written:
        wrapper_metadata, _ = exporter.parse_frontmatter_skill(skill_path)
        skill_name = wrapper_metadata["name"]
        source_metadata, _ = exporter.parse_frontmatter_skill(
            REPO_ROOT / "skills" / skill_name / "SKILL.md"
        )
        assert wrapper_metadata["description"] == source_metadata["description"]


def test_parse_rejects_missing_frontmatter(tmp_path: Path):
    exporter = load_exporter()
    path = tmp_path / "bad.md"
    path.write_text("No frontmatter\n", encoding="utf-8")

    with pytest.raises(exporter.SkillParseError, match="missing YAML frontmatter"):
        exporter.parse_frontmatter_skill(path)
