"""Tests and canaries for the model-routing parity gate (``scripts/check_model_routing_parity.py``).

The gate holds each agent definition's ``model:`` equal to its row in the routing rule's tier
table, the declared consultant floor aside. Each finding kind has a canary that feeds the known-bad
shape and asserts the gate flags it; the repository itself must read in parity.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_model_routing_parity as parity  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent
TABLE = (
    "## Agent Model Routing\n\n### Tier Table\n\n"
    "| Agent | Tier | Alias | Rationale |\n|---|---|---|---|\n"
    "| `verifier` | H | `opus` | gate |\n"
    "| `implementer` | M | `sonnet` | steps |\n"
    "| `discipline-consultant` | H | `opus` | floor is `sonnet` |\n\n"
    "Full policy elsewhere.\n"
)
IN_PARITY = {"verifier": "opus", "implementer": "sonnet", "discipline-consultant": "sonnet"}


def definition(name: str, model: str) -> str:
    return f"---\nname: {name}\ndescription: x\nmodel: {model}\n---\n\nBody.\n"


def kinds(findings: list[parity.Finding]) -> list[tuple[str, str]]:
    return [(finding.kind, finding.agent) for finding in findings]


def checkout(tmp_path: Path, rule: str, models: dict[str, str]) -> Path:
    (tmp_path / "rules/swe").mkdir(parents=True)
    (tmp_path / parity.ROUTING_RULE).write_text(rule, encoding="utf-8")
    (tmp_path / "agents").mkdir()
    for name, model in models.items():
        (tmp_path / "agents" / f"{name}.md").write_text(definition(name, model), encoding="utf-8")
    return tmp_path


def test_the_repository_reads_in_parity():
    assert parity.main(["--repo-root", str(REPO_ROOT)]) == 0


def test_a_table_and_definitions_that_agree_have_no_finding():
    assert parity.judge(parity.table_aliases(TABLE), IN_PARITY) == []


def test_flag_a_definition_whose_model_is_not_its_rows_alias():
    models = {**IN_PARITY, "implementer": "opus"}

    assert kinds(parity.judge(parity.table_aliases(TABLE), models)) == [("mismatch", "implementer")]


def test_flag_an_agent_the_table_does_not_list():
    models = {**IN_PARITY, "doc-engineer": "claude-haiku-4-5"}

    assert kinds(parity.judge(parity.table_aliases(TABLE), models)) == [("no-row", "doc-engineer")]


def test_flag_a_row_naming_no_definition():
    models = {key: value for key, value in IN_PARITY.items() if key != "verifier"}

    assert kinds(parity.judge(parity.table_aliases(TABLE), models)) == [("no-agent", "verifier")]


def test_flag_a_declared_floor_the_definition_no_longer_carries():
    models = {**IN_PARITY, "discipline-consultant": "opus"}

    assert kinds(parity.judge(parity.table_aliases(TABLE), models)) == [
        ("stale-floor", "discipline-consultant")
    ]


def test_reject_a_rule_with_no_tier_table(tmp_path, capsys):
    repo = checkout(tmp_path, "## Agent Model Routing\n\nNo table here.\n", IN_PARITY)

    assert parity.main(["--repo-root", str(repo)]) == 1
    assert "no-table" in capsys.readouterr().out


def test_reject_a_checkout_whose_definitions_disagree_with_the_table(tmp_path, capsys):
    repo = checkout(tmp_path, TABLE, {**IN_PARITY, "verifier": "sonnet"})

    assert parity.main(["--repo-root", str(repo)]) == 1
    assert "mismatch: verifier" in capsys.readouterr().out


def test_a_model_line_with_a_trailing_comment_reads_as_its_value():
    text = "---\nname: doc-engineer\nmodel: claude-haiku-4-5  # pinned full ID\n---\n"

    assert parity.frontmatter_model(text) == ("doc-engineer", "claude-haiku-4-5")


def test_a_file_without_an_agent_name_is_not_a_definition():
    assert parity.frontmatter_model("# Agents\n\nA catalog page.\n") is None
