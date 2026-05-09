from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTER_PATH = REPO_ROOT / "codex" / "config" / "export-codex-command-skills.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_codex_command_skills", EXPORTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_command_skills_writes_wrapper_without_command_body(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / "skills"

    written = exporter.export_command_skills(REPO_ROOT, out_dir)

    skill = out_dir / "praxion-command-co" / "SKILL.md"
    assert skill in written
    text = skill.read_text(encoding="utf-8")
    assert "name: praxion-command-co" in text
    assert "This is a Codex command-skill wrapper for a Praxion slash command." in text
    assert f"`{(REPO_ROOT / 'commands' / 'co.md').resolve().as_posix()}`" in text
    assert "Create a commit for the current staged changes" not in text
    assert "Treat any user text after the command name as `$ARGUMENTS`." in text


def test_export_command_skills_preserves_all_canonical_descriptions(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / "skills"

    written = exporter.export_command_skills(REPO_ROOT, out_dir)

    for skill_path in written:
        wrapper_metadata, _ = exporter.parse_frontmatter_command(skill_path)
        command_name = wrapper_metadata["name"].removeprefix("praxion-command-")
        source_metadata, _ = exporter.parse_frontmatter_command(
            REPO_ROOT / "commands" / f"{command_name}.md"
        )
        assert wrapper_metadata["description"] == source_metadata["description"]


def test_export_command_skills_skips_command_guidance_files(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / "skills"

    exporter.export_command_skills(REPO_ROOT, out_dir)

    assert not (out_dir / "praxion-command-README" / "SKILL.md").exists()
    assert not (out_dir / "praxion-command-CLAUDE" / "SKILL.md").exists()


def test_parse_rejects_missing_description(tmp_path: Path):
    exporter = load_exporter()
    path = tmp_path / "bad.md"
    path.write_text("---\nargument-hint: [x]\n---\n\nBody\n", encoding="utf-8")

    try:
        exporter.parse_frontmatter_command(path)
    except exporter.CommandParseError as exc:
        assert "missing required frontmatter key: description" in str(exc)
    else:
        raise AssertionError("expected CommandParseError")
