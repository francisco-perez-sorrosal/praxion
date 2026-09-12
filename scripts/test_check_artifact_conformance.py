"""Tests for check_artifact_conformance.py -- C01-05/N01-03/S01-04 canary.

Each test builds a minimal substrate tree under `tmp_path` (skills/, agents/,
commands/, rules/, plugin.json) rather than pointing at the live repo -- the
golden bad-cases construct the exact drifted shapes each check exists to
catch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_artifact_conformance import CHECK_IDS, classify  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _skill_md(
    *, name: str = "my-skill", description: str = "Does a thing. Triggers: doing things."
) -> str:
    # Quoted: a description containing a colon (e.g. "Creating and managing X:
    # details") is invalid unquoted YAML, same defect check_frontmatter_parses.py
    # documents.
    quoted = description.replace('"', '\\"')
    return f'---\nname: {name}\ndescription: "{quoted}"\n---\n\n# {name}\n'


def _agent_md(
    *, name: str = "my-agent", description: str = "Does a thing", tools: str = "Read, Grep"
) -> str:
    return f"---\nname: {name}\ndescription: {description}\ntools: {tools}\n---\n\nBody.\n"


def _write_plugin_json(tmp_path: Path, agents: list[str]) -> None:
    _write(tmp_path / ".claude-plugin" / "plugin.json", json.dumps({"agents": agents}))


def _write_agents(tmp_path: Path, names: list[str]) -> None:
    for name in names:
        _write(tmp_path / "agents" / f"{name}.md", _agent_md(name=name))


def _base_tree(tmp_path: Path, agents: list[str]) -> None:
    _write_plugin_json(tmp_path, [f"./agents/{n}.md" for n in agents])
    _write_agents(tmp_path, agents)


def test_check_ids_declares_all_twelve() -> None:
    assert CHECK_IDS == (
        "C01",
        "C02",
        "C03",
        "C04",
        "C05",
        "N01",
        "N02",
        "N03",
        "S01",
        "S02",
        "S03",
        "S04",
    )


# -- C01/S01 ------------------------------------------------------------------


def test_c01_passes_when_every_skill_dir_has_skill_md(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "code-review" / "SKILL.md", _skill_md(name="code-review"))
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "C01"] == []


def test_c01_flags_skill_dir_missing_skill_md(tmp_path: Path) -> None:
    (tmp_path / "skills" / "hollow-skill").mkdir(parents=True)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "C01"]
    assert any("hollow-skill" in f["entity"] for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_c01_skips_when_skills_dir_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["C01"]["reason"] == "substrate-absent"


def test_s01_flags_missing_description(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "no-desc" / "SKILL.md", "---\nname: no-desc\n---\n\nBody.\n")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "S01"]
    assert any("no-desc" in f["entity"] for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_s01_flags_empty_description(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "blank-desc" / "SKILL.md",
        '---\nname: blank-desc\ndescription: ""\n---\n\nBody.\n',
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "S01"]
    assert any("blank-desc" in f["entity"] for f in findings)


def test_c02_flags_same_shape_as_warn(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "no-desc" / "SKILL.md", "---\nname: no-desc\n---\n\nBody.\n")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "C02"]
    assert any(f["severity"] == "warn" for f in findings)


# -- C03/S02 ------------------------------------------------------------------


def test_c03_passes_when_agent_has_required_fields(tmp_path: Path) -> None:
    _write_agents(tmp_path, ["researcher"])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "C03"] == []


def test_c03_flags_missing_tools_field(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents" / "ghost.md",
        "---\nname: ghost\ndescription: does things\n---\n\nBody.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "C03"]
    assert any(f["entity"] == "agents/ghost.md" and "tools" in f["message"] for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_c03_excludes_readme_and_claude_md(tmp_path: Path) -> None:
    _write_agents(tmp_path, ["researcher"])
    _write(tmp_path / "agents" / "README.md", "placeholder\n")
    _write(tmp_path / "agents" / "CLAUDE.md", "# instructions\n")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "C03"] == []


def test_s02_flags_empty_name(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents" / "hollow.md",
        '---\nname: ""\ndescription: x\ntools: Read\n---\n\nBody.\n',
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "S02"]
    assert any(f["entity"] == "agents/hollow.md" and "name" in f["message"] for f in findings)


# -- C04 ------------------------------------------------------------------------


def test_c04_passes_with_frontmatter_description(tmp_path: Path) -> None:
    _write(
        tmp_path / "commands" / "release.md", '---\ndescription: "Cut a release."\n---\n\nBody.\n'
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "C04"] == []


def test_c04_passes_with_header_comment_no_frontmatter(tmp_path: Path) -> None:
    _write(tmp_path / "commands" / "quick.md", "<!-- Cuts a release. -->\n\nBody.\n")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "C04"] == []


def test_c04_flags_empty_description(tmp_path: Path) -> None:
    _write(tmp_path / "commands" / "empty.md", '---\ndescription: ""\n---\n\nBody.\n')
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "C04"]
    assert any("empty.md" in f["entity"] for f in findings)
    assert all(f["severity"] == "warn" for f in findings)


def test_c04_flags_todo_placeholder(tmp_path: Path) -> None:
    _write(tmp_path / "commands" / "stub.md", "---\ndescription: TODO\n---\n\nBody.\n")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "C04"]
    assert any("stub.md" in f["entity"] for f in findings)


def test_c04_flags_angle_bracket_stub(tmp_path: Path) -> None:
    _write(tmp_path / "commands" / "stub2.md", "---\ndescription: <fill this in>\n---\n\nBody.\n")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "C04"]
    assert any("stub2.md" in f["entity"] for f in findings)


def test_c04_flags_no_description_and_no_header_comment(tmp_path: Path) -> None:
    _write(tmp_path / "commands" / "bare.md", "Just body text, no comment or frontmatter.\n")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "C04"]
    assert any("bare.md" in f["entity"] for f in findings)


# -- C05 ------------------------------------------------------------------------


def test_c05_passes_when_counts_match(tmp_path: Path) -> None:
    _base_tree(tmp_path, ["researcher", "sentinel"])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "C05"] == []


def test_c05_flags_count_mismatch(tmp_path: Path) -> None:
    _write_plugin_json(tmp_path, ["./agents/researcher.md"])
    _write_agents(tmp_path, ["researcher", "orphan"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "C05"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "fail"


def test_c05_skips_when_plugin_json_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["C05"]["reason"] == "substrate-absent"


# -- N01 ------------------------------------------------------------------------


def test_n01_flags_non_kebab_case_dir(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "My_Skill" / "SKILL.md", _skill_md(name="My_Skill"))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "N01"]
    assert any("My_Skill" in f["entity"] for f in findings)
    assert all(f["severity"] == "warn" for f in findings)


def test_n01_flags_crafting_skill_missing_suffix(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "widget-authoring" / "SKILL.md",
        _skill_md(
            name="widget-authoring",
            description="Creating and managing widget commands: types, lifecycle. Triggers: making widgets.",
        ),
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "N01"]
    assert any("widget-authoring" in f["entity"] for f in findings)


def test_n01_does_not_flag_mention_inside_triggers_clause(tmp_path: Path) -> None:
    """The 'crafting' phrase only counts in the opening clause -- a mention
    inside `Triggers:` (e.g. a trigger phrase borrowing the verb) must not
    false-positive a skill whose stated purpose is something else."""
    _write(
        tmp_path / "skills" / "unrelated-topic" / "SKILL.md",
        _skill_md(
            name="unrelated-topic",
            description="Some unrelated capability. Triggers: authoring widgets, other things.",
        ),
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "N01"] == []


def test_n01_does_not_flag_correctly_suffixed_crafting_skill(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "widget-crafting" / "SKILL.md",
        _skill_md(name="widget-crafting", description="Creating and managing widgets."),
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "N01"] == []


def test_n01_flags_language_skill_missing_development_suffix(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "python" / "SKILL.md", _skill_md(name="python"))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "N01"]
    assert any(f["entity"] == "skills/python" for f in findings)


def test_n01_does_not_flag_correctly_suffixed_language_skill(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "python-development" / "SKILL.md",
        _skill_md(name="python-development"),
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "N01"] == []


# -- N02 ------------------------------------------------------------------------


def test_n02_flags_non_kebab_agent_stem(tmp_path: Path) -> None:
    _write(tmp_path / "agents" / "MyAgent.md", _agent_md(name="MyAgent"))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "N02"]
    assert any("MyAgent" in f["entity"] for f in findings)


def test_n02_passes_for_kebab_agent_stem(tmp_path: Path) -> None:
    _write_agents(tmp_path, ["researcher"])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "N02"] == []


# -- N03 ------------------------------------------------------------------------


def test_n03_flags_unrecognized_skill_key(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "odd-skill" / "SKILL.md",
        "---\nname: odd-skill\ndescription: does a thing\nbogus_field: 1\n---\n\nBody.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "N03"]
    assert any("bogus_field" in f["message"] for f in findings)
    assert all(f["severity"] == "warn" for f in findings)


def test_n03_accepts_recognized_skill_keys(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "clean-skill" / "SKILL.md",
        "---\nname: clean-skill\ndescription: does a thing\nallowed-tools: [Read]\npaths: ['**/*.md']\n---\n\nBody.\n",
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "N03"] == []


def test_n03_flags_unrecognized_agent_key(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents" / "odd-agent.md",
        "---\nname: odd-agent\ndescription: does things\ntools: Read\nbogus_field: 1\n---\n\nBody.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "N03"]
    assert any("bogus_field" in f["message"] for f in findings)


def test_n03_accepts_recognized_agent_keys(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents" / "clean-agent.md",
        "---\nname: clean-agent\ndescription: does things\ntools: Read\nmaxTurns: 50\nbackground: true\n---\n\nBody.\n",
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "N03"] == []


# -- S03 ------------------------------------------------------------------------


def test_s03_passes_when_first_line_is_h2(tmp_path: Path) -> None:
    _write(tmp_path / "rules" / "swe" / "good-rule.md", "## Good Rule\n\nBody.\n")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "S03"] == []


def test_s03_flags_missing_h2_heading(tmp_path: Path) -> None:
    _write(tmp_path / "rules" / "swe" / "bad-rule.md", "Some prose with no heading.\n")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "S03"]
    assert any("bad-rule.md" in f["entity"] for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_s03_skips_rule_frontmatter_before_checking_heading(tmp_path: Path) -> None:
    """A rule with its own `paths:` frontmatter is checked against the first
    non-blank line of the BODY, not the file -- `---` is not itself the
    violation."""
    _write(
        tmp_path / "rules" / "swe" / "scoped-rule.md",
        "---\npaths:\n  - '**/*.py'\n---\n\n## Scoped Rule\n\nBody.\n",
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "S03"] == []


def test_s03_excludes_readme(tmp_path: Path) -> None:
    _write(tmp_path / "rules" / "README.md", "Not a rule, no heading needed.\n")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "S03"] == []


# -- S04 ------------------------------------------------------------------------


def test_s04_passes_when_hint_is_substituted(tmp_path: Path) -> None:
    _write(
        tmp_path / "commands" / "greet.md",
        '---\nargument-hint: "[name]"\n---\n\nHello $ARGUMENTS.\n',
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "S04"] == []


def test_s04_flags_declared_hint_never_substituted(tmp_path: Path) -> None:
    _write(
        tmp_path / "commands" / "unused-hint.md",
        '---\nargument-hint: "[name]"\n---\n\nThis command never uses the argument.\n',
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "S04"]
    assert any("unused-hint.md" in f["entity"] for f in findings)
    assert all(f["severity"] == "warn" for f in findings)


def test_s04_does_not_examine_commands_without_hint(tmp_path: Path) -> None:
    _write(tmp_path / "commands" / "no-args.md", "---\ndescription: no args needed\n---\n\nBody.\n")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "S04"] == []
    assert report["examined"]["S04"]["command_files_with_hint"] == 0
