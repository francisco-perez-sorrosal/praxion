"""Tests for check_registry_projection.py -- X01/X02/X05/X06/EC01/EC02 canary.

Each test builds a minimal substrate tree under `tmp_path` (plugin.json / agents/ /
coordination-details.md / README.md / diagram `.mmd` / skills/ / commands/ / rules/)
rather than pointing at the live repo -- the golden bad-cases construct the exact
drifted shapes each check exists to catch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_registry_projection import CHECK_IDS, classify  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_plugin_json(tmp_path: Path, agents: list[str]) -> None:
    _write(tmp_path / ".claude-plugin" / "plugin.json", json.dumps({"agents": agents}))


def _write_agent_files(tmp_path: Path, names: list[str]) -> None:
    for name in names:
        _write(tmp_path / "agents" / f"{name}.md", f"# {name}\n")
    _write(tmp_path / "agents" / "README.md", "placeholder\n")


def _write_roster(tmp_path: Path, names: list[str]) -> None:
    rows = "".join(f"| `{n}` | ... | Yes |\n" for n in names)
    text = f"## Agent Roster\n\n| Agent | Output | Bg Safe |\n|---|---|---|\n{rows}\n## Next\n"
    _write(
        tmp_path / "skills" / "software-planning" / "references" / "coordination-details.md",
        text,
    )


def _write_readme_table(tmp_path: Path, names: list[str]) -> None:
    newline = "\n"
    rows = "".join(f"| `{n}` | does things | - |{newline}" for n in names)
    loop_rows = "".join(f"| `{n}` | role | - |{newline}" for n in names)
    text = (
        "# Agents\n\n"
        "| Agent | Description | Skills Used |\n"
        "|-------|-------------|-------------|\n"
        f"{rows}\n"
        "### Loop Participation\n\n"
        "| Agent | Forward pipeline role | Loop participation |\n"
        "|-------|------------------------|---------------------|\n"
        f"{loop_rows}"
    )
    _write(tmp_path / "agents" / "README.md", text)


def _write_diagram(tmp_path: Path, names: list[str]) -> None:
    body = "flowchart TD\n" + "\n".join(f'    N{i}["{n}"]' for i, n in enumerate(names))
    _write(
        tmp_path
        / "agents"
        / "diagrams"
        / "agent-pipeline-flowchart"
        / "src"
        / "agent-pipeline-flowchart.mmd",
        body,
    )


def _base_tree(tmp_path: Path, agents: list[str]) -> None:
    _write_plugin_json(tmp_path, [f"./agents/{n}.md" for n in agents])
    _write_agent_files(tmp_path, agents)
    _write_roster(tmp_path, agents)
    _write_readme_table(tmp_path, agents)
    _write_diagram(tmp_path, agents)


_AGENTS = ["researcher", "sentinel"]


def test_check_ids_declares_all_six() -> None:
    assert CHECK_IDS == ("X01", "X02", "X05", "X06", "EC01", "EC02")


# -- X01 --------------------------------------------------------------------


def test_x01_passes_when_all_agent_paths_resolve(tmp_path: Path) -> None:
    _base_tree(tmp_path, _AGENTS)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "X01"] == []


def test_x01_flags_missing_agent_path(tmp_path: Path) -> None:
    _write_plugin_json(tmp_path, ["./agents/researcher.md", "./agents/ghost.md"])
    _write_agent_files(tmp_path, ["researcher"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "X01"]
    assert any("ghost" in f["entity"] for f in findings)


def test_x01_skips_when_plugin_json_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["X01"]["reason"] == "substrate-absent"


# -- X02 --------------------------------------------------------------------


def test_x02_passes_when_skills_and_commands_are_loadable(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "code-review" / "SKILL.md", "content\n")
    _write(tmp_path / "commands" / "release.md", "content\n")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "X02"] == []


def test_x02_flags_skill_dir_missing_skill_md(tmp_path: Path) -> None:
    (tmp_path / "skills" / "hollow-skill").mkdir(parents=True)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "X02"]
    assert any("hollow-skill" in f["entity"] for f in findings)


def test_x02_flags_empty_command_file(tmp_path: Path) -> None:
    _write(tmp_path / "commands" / "empty.md", "")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "X02"]
    assert any("empty.md" in f["entity"] for f in findings)


# -- X05 ----------------------------------------------------------------------


def test_x05_passes_when_roster_matches_agent_files(tmp_path: Path) -> None:
    _base_tree(tmp_path, _AGENTS)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "X05"] == []


def test_x05_flags_roster_name_missing_agent_file(tmp_path: Path) -> None:
    _write_agent_files(tmp_path, ["researcher"])
    _write_roster(tmp_path, ["researcher", "ghost"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "X05"]
    assert any(f["entity"] == "ghost" for f in findings)


def test_x05_flags_agent_file_missing_from_roster(tmp_path: Path) -> None:
    _write_agent_files(tmp_path, ["researcher", "orphan"])
    _write_roster(tmp_path, ["researcher"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "X05"]
    assert any(f["entity"] == "orphan" for f in findings)


def test_x05_skips_when_roster_file_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["X05"]["reason"] == "substrate-absent"


# -- X06 ----------------------------------------------------------------------


def test_x06_passes_when_readme_table_matches_agent_files(tmp_path: Path) -> None:
    _base_tree(tmp_path, _AGENTS)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "X06"] == []


def test_x06_flags_readme_row_missing_agent_file(tmp_path: Path) -> None:
    _write_agent_files(tmp_path, ["researcher"])
    _write_readme_table(tmp_path, ["researcher", "ghost"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "X06"]
    assert any(f["entity"] == "ghost" for f in findings)


def test_x06_skips_when_readme_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["X06"]["reason"] == "substrate-absent"


# -- EC01 -----------------------------------------------------------------------


def test_ec01_passes_when_diagram_nodes_resolve(tmp_path: Path) -> None:
    _base_tree(tmp_path, _AGENTS)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "EC01"] == []


def test_ec01_flags_diagram_node_missing_agent_file(tmp_path: Path) -> None:
    _write_agent_files(tmp_path, ["researcher"])
    _write_diagram(tmp_path, ["researcher", "ghost"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "EC01"]
    assert any(f["entity"] == "ghost" for f in findings)


def test_ec01_does_not_flag_agent_absent_from_diagram(tmp_path: Path) -> None:
    """One-directional: a real agent left out of the forward-pipeline diagram
    (e.g. an on-demand tool like roadmap-cartographer) is not itself a finding."""
    _write_agent_files(tmp_path, ["researcher", "roadmap-cartographer"])
    _write_diagram(tmp_path, ["researcher"])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "EC01"] == []


def test_ec01_skips_when_diagram_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["EC01"]["reason"] == "substrate-absent"


# -- EC02 -----------------------------------------------------------------------


def _write_ec02_surfaces(tmp_path: Path, *, mentions: list[str]) -> None:
    body = "\n".join(f"See `{m}` for details." for m in mentions)
    _write(tmp_path / "CLAUDE.md", body)
    _write(tmp_path / "agents" / "researcher.md", "# researcher\n")


def test_ec02_passes_when_all_artifacts_referenced(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "code-review" / "SKILL.md", "content\n")
    _write(tmp_path / "commands" / "release.md", "content\n")
    _write_ec02_surfaces(tmp_path, mentions=["code-review", "release"])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "EC02"] == []


def test_ec02_flags_orphaned_skill(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "unmentioned-skill" / "SKILL.md", "content\n")
    _write_ec02_surfaces(tmp_path, mentions=[])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "EC02"]
    assert any("unmentioned-skill" in f["entity"] for f in findings)
    assert all(f["severity"] == "warn" for f in findings)


def test_ec02_flags_orphaned_command(tmp_path: Path) -> None:
    _write(tmp_path / "commands" / "unmentioned-command.md", "content\n")
    _write_ec02_surfaces(tmp_path, mentions=[])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "EC02"]
    assert any("unmentioned-command" in f["entity"] for f in findings)


def test_ec02_flags_orphaned_rule(tmp_path: Path) -> None:
    _write(tmp_path / "rules" / "swe" / "unmentioned-rule.md", "content\n")
    _write_ec02_surfaces(tmp_path, mentions=[])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "EC02"]
    assert any("unmentioned-rule" in f["entity"] for f in findings)


def test_ec02_does_not_flag_rule_referenced_by_a_sibling_rule(tmp_path: Path) -> None:
    _write(tmp_path / "rules" / "swe" / "target-rule.md", "content\n")
    _write(tmp_path / "rules" / "swe" / "citing-rule.md", "see `target-rule.md`\n")
    _write_ec02_surfaces(tmp_path, mentions=[])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "EC02"]
    assert not any("target-rule" in f["entity"] for f in findings)


def test_ec02_skips_when_no_surfaces_readable(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["EC02"]["reason"] == "substrate-absent"
