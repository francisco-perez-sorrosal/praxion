"""Frontmatter parsing in the Codex rules bridge.

A rule's ``paths:`` decides whether Codex routes it by file or loads it as an
always-on rule, so a form the parser misreads silently turns a path-scoped rule
into one every Codex session pays for.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PARSING_PATH = REPO_ROOT / "codex" / "config" / "rules_bridge_parsing.py"


def _load_parsing():
    spec = importlib.util.spec_from_file_location("rules_bridge_parsing_under_test", PARSING_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parsing = _load_parsing()


def _paths(frontmatter: str) -> object:
    return parsing.parse_rule_frontmatter(frontmatter.splitlines(), Path("rule.md")).get("paths")


def test_inline_array_paths_yield_each_glob():
    assert _paths('paths: ["skills/a/SKILL.md", ".github/**/*.md"]\ncore: false') == [
        "skills/a/SKILL.md",
        ".github/**/*.md",
    ]


def test_block_list_paths_still_yield_each_glob():
    assert _paths('paths:\n  - "rules/**"\n  - docs/*.md\ncore: false') == ["rules/**", "docs/*.md"]


def test_inline_array_keeps_commas_inside_quoted_globs():
    assert _paths("paths: ['src/{a,b}/*.py', \"x.md\"]") == ["src/{a,b}/*.py", "x.md"]


def test_inline_value_that_is_not_a_sequence_is_refused():
    with pytest.raises(parsing.RuleParseError, match="unsupported paths value"):
        _paths("paths: rules/**")


@pytest.mark.parametrize(
    "rule",
    [
        "rules/swe/vcs/pr-conventions.md",
        "rules/swe/gate-liveness.md",
        "rules/swe/plugin-install-conventions.md",
        "rules/ml/experiment-commit-conventions.md",
    ],
)
def test_repository_rules_with_inline_paths_are_path_scoped(rule):
    lines = (REPO_ROOT / rule).read_text(encoding="utf-8").splitlines()
    closing = lines.index("---", 1)
    globs = parsing.parse_rule_frontmatter(lines[1:closing], Path(rule)).get("paths")
    assert globs, f"{rule} parsed with no path globs, so Codex would load it always-on"


RULE = "---\npaths:\n  - 'docs/**'\n---\n## Rule\n\nThe whole rule.\n"
RESIDENT = (
    "---\nresident_of: rules/swe/rule.md\ncodex:\n  load: exclude\n---\n## Rule\n\nOne line.\n"
)


def _write_rules(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / "rules" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_a_resident_beside_its_rule_leaves_the_manifests_rules_unchanged(tmp_path: Path) -> None:
    alone = parsing.build_manifest(_write_rules(tmp_path / "alone", {"swe/rule.md": RULE}))
    both = parsing.build_manifest(
        _write_rules(tmp_path / "both", {"swe/rule.md": RULE, "swe/rule-resident.md": RESIDENT})
    )

    assert [rule["id"] for rule in both["rules"]] == ["rules::swe::rule"]
    assert [rule["relpath"] for rule in both["rules"]] == [
        rule["relpath"] for rule in alone["rules"]
    ]


@pytest.mark.parametrize(
    "text",
    [
        RESIDENT,
        RULE,
        "---\n'resident_of': \"rules/swe/rule.md\"\n---\nBody.\n",
        "---\nresident_of:\n---\nBody.\n",
        "---\n  resident_of: rules/swe/rule.md\n---\nBody.\n",
        "---\nresident_of: rules/swe/rule.md\nBody, never closed.\n",
        "No frontmatter; resident_of: rules/swe/rule.md\n",
        "---\npaths: ['docs/**']\n---\nresident_of: rules/swe/rule.md\n",
    ],
    ids=["resident", "rule", "quoted", "empty", "indented", "unclosed", "none", "in-body"],
)
def test_the_bridges_resident_check_agrees_with_the_shared_reader(text: str) -> None:
    from scripts._resident_of import resident_parent

    assert parsing.is_resident(text) is bool(resident_parent(text))
