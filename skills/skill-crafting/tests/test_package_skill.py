"""Behavioral tests for `skills/skill-crafting/scripts/package_skill.py`.

A claude.ai upload rejects any frontmatter field outside the open-standard core, so the
packager warns when the skill it just archived carries one. The warning never blocks packaging.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

PACKAGER = Path(__file__).resolve().parents[1] / "scripts" / "package_skill.py"
PROBE = "probe-skill"
DESCRIPTION = "Use when probing the skill packager with a minimal skill."


def _load_packager() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_package_skill_under_test", PACKAGER)
    assert spec is not None, f"cannot load {PACKAGER}"
    assert spec.loader is not None, f"cannot load {PACKAGER}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package = _load_packager()


def write_skill(parent: Path, extra: tuple[str, ...] = ()) -> Path:
    skill_dir = parent / PROBE
    skill_dir.mkdir(parents=True)
    lines = ["---", f"name: {PROBE}", f"description: {DESCRIPTION}", *extra, "---", "# Probe", ""]
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return skill_dir


def test_a_skill_with_claude_code_fields_packages_and_names_them_in_a_warning(tmp_path, capsys):
    skill_dir = write_skill(tmp_path, ("argument-hint: [path]", "disable-model-invocation: true"))

    code = package.package_skill(skill_dir, tmp_path / "dist")

    out = capsys.readouterr().out
    assert code == 0
    assert (tmp_path / "dist" / f"{PROBE}.skill").is_file()
    assert "argument-hint, disable-model-invocation" in out
    assert "claude.ai" in out


def test_a_skill_with_only_open_standard_fields_packages_without_a_warning(tmp_path, capsys):
    skill_dir = write_skill(tmp_path, ("license: MIT",))

    code = package.package_skill(skill_dir, tmp_path / "dist")

    assert code == 0
    assert "Warning" not in capsys.readouterr().out
    with ZipFile(tmp_path / "dist" / f"{PROBE}.skill") as archive:
        assert archive.namelist() == [f"{PROBE}/SKILL.md"]
