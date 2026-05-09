from __future__ import annotations

import importlib.util
from pathlib import Path


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
    assert "`skills/ml-training/SKILL.md`" in text
    description_line = next(line for line in text.splitlines() if line.startswith("description: "))
    description = description_line.split(": ", 1)[1]
    assert description.startswith("'") and description.endswith("'")
    source_metadata, _ = exporter.parse_frontmatter_skill(REPO_ROOT / "skills" / "ml-training" / "SKILL.md")
    source_description = source_metadata["description"]
    assert description[1:-1] == source_description


def test_parse_rejects_missing_frontmatter(tmp_path: Path):
    exporter = load_exporter()
    path = tmp_path / "bad.md"
    path.write_text("No frontmatter\n", encoding="utf-8")

    try:
        exporter.parse_frontmatter_skill(path)
    except exporter.SkillParseError as exc:
        assert "missing YAML frontmatter" in str(exc)
    else:
        raise AssertionError("expected SkillParseError")
