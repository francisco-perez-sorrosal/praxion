"""A lean arm relocates text, it never loses it on a host without hooks: Cursor and Codex deliver
only what their rule exports carry, so a lean copy that reaches less of the moved rule than the
checkout, narrows Codex's always-on listing, breaks an export, or hands a hook text that no rule
file both hosts carry is refused naming the section, the line or the host."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from praxion_evals.adherence.moves import arms, declaration, reach
from praxion_evals.adherence.moves.arms import ArmSet
from praxion_evals.adherence.moves.model import MoveDeclaration
from praxion_evals.adherence.moves.reach import ReachError

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_MOVE = "git-conventions"
ADR_MOVE = "adr-conventions"
GIT_RULE = "rules/swe/vcs/git-conventions.md"
GIT_HOOK = "hooks/inject_git_conventions_at_use.py"
STAGING_SECTION = "Staging Discipline"
READ_TREES = ("rules", "lib", "hooks")
READ_FILES = (
    reach.CURSOR_EXPORTER,
    reach.CODEX_EXPORTER,
    *(
        f"codex/config/{path.name}"
        for path in (REPO_ROOT / "codex/config").glob("rules_bridge_*.py")
    ),
    "claude/config/CLAUDE.md.tmpl",  # read by the build's pinning
    "scripts/render_claude_md.py",
)
INVENTED_LINE = "A line that no rule file holds."
EMBEDDING_HOOK = (
    "import json\n"
    'print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",'
    f' "additionalContext": "{INVENTED_LINE}"}}}}))\n'
)


@pytest.fixture(scope="module")
def checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("reach") / "checkout"
    for tree in READ_TREES:
        shutil.copytree(REPO_ROOT / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    for relpath in READ_FILES:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relpath, root / relpath)
    return root


@pytest.fixture(scope="module")
def first_move(checkout: Path, tmp_path_factory: pytest.TempPathFactory) -> ArmSet:
    return _built(declaration.kit(GIT_MOVE), checkout, tmp_path_factory.mktemp("first"))


@pytest.fixture(scope="module")
def second_move(checkout: Path, tmp_path_factory: pytest.TempPathFactory) -> ArmSet:
    return _built(declaration.kit(ADR_MOVE), checkout, tmp_path_factory.mktemp("second"))


def _built(declared: MoveDeclaration, checkout: Path, workspace: Path) -> ArmSet:
    built = arms.build(declared, checkout, workspace)
    assert isinstance(built, ArmSet), built
    return built


def _lean_variant(first_move: ArmSet, tmp_path: Path) -> Path:
    """A writable copy of the git kit's lean arm for a known-bad edit."""
    variant = tmp_path / "lean"
    shutil.copytree(first_move.arms["lean"].copy, variant, symlinks=True)
    return variant


def _require(copy: Path, checkout: Path) -> None:
    scripts = arms.hook_scripts(declaration.kit(GIT_MOVE).arms.lean)
    reach.require_reach(declaration.kit(GIT_MOVE), checkout, copy, scripts)


def _refusal(copy: Path, checkout: Path) -> str:
    with pytest.raises(ReachError) as refused:
        _require(copy, checkout)
    return str(refused.value)


# -- What a lean arm may do -------------------------------------------------------------------


def test_the_git_conventions_lean_copy_reaches_every_section_on_both_hosts(first_move, checkout):
    _require(first_move.arms["lean"].copy, checkout)


def test_a_path_scoped_rule_keeping_codex_always_on_reaches_as_today(second_move, checkout):
    declared = declaration.kit(ADR_MOVE)

    reach.require_reach(declared, checkout, second_move.arms["lean"].copy, [])


def test_a_lean_copy_changing_only_the_manifest_loses_nothing(first_move, checkout):
    lean = first_move.arms["lean"].copy
    manifest_differs = (lean / "rules/_manifest.yaml").read_bytes() != (
        checkout / "rules/_manifest.yaml"
    ).read_bytes()

    assert manifest_differs, "the lean copy leaves the manifest alone"
    _require(lean, checkout)


# -- What a lean arm may not do ---------------------------------------------------------------


def test_a_section_missing_from_the_moved_rule_is_refused_naming_it_and_both_hosts(
    first_move, checkout, tmp_path
):
    lean = _lean_variant(first_move, tmp_path)
    rule = lean / GIT_RULE
    text = rule.read_text(encoding="utf-8")
    rule.write_text(
        text.replace(f"### {STAGING_SECTION}\n", "### Renamed Away\n"), encoding="utf-8"
    )

    refusal = _refusal(lean, checkout)

    assert f'"{STAGING_SECTION}"' in refusal
    assert "cursor" in refusal
    assert "codex" in refusal


def test_a_codex_always_on_listing_turned_path_scoped_is_refused_naming_the_section(
    first_move, checkout, tmp_path
):
    lean = _lean_variant(first_move, tmp_path)
    rule = lean / GIT_RULE
    text = rule.read_text(encoding="utf-8")
    rule.write_text(text.replace("---\n", "---\npaths:\n  - src/**\n", 1), encoding="utf-8")

    refusal = _refusal(lean, checkout)

    assert f'"{STAGING_SECTION}"' in refusal
    assert refusal.endswith("always-on on codex")
    assert "cursor" not in refusal


def test_a_hook_embedding_text_read_from_no_rule_file_is_refused_naming_the_line(
    first_move, checkout, tmp_path
):
    lean = _lean_variant(first_move, tmp_path)
    (lean / GIT_HOOK).write_text(EMBEDDING_HOOK, encoding="utf-8")

    refusal = _refusal(lean, checkout)

    assert INVENTED_LINE in refusal
    assert GIT_HOOK in refusal


def test_a_hook_that_cannot_be_observed_is_refused_naming_it(first_move, checkout, tmp_path):
    lean = _lean_variant(first_move, tmp_path)
    (lean / GIT_HOOK).write_text("raise SystemExit(3)\n", encoding="utf-8")

    refusal = _refusal(lean, checkout)

    assert GIT_HOOK in refusal
    assert "cannot be observed" in refusal


def test_a_rule_file_the_codex_bridge_cannot_parse_is_refused_naming_it(
    first_move, checkout, tmp_path
):
    lean = _lean_variant(first_move, tmp_path)
    (lean / "rules/swe/vcs/untitled.md").write_text("- a line with no title\n", encoding="utf-8")

    refusal = _refusal(lean, checkout)

    assert "untitled.md" in refusal
    assert "level-2 title" in refusal


def test_a_checkout_without_the_exporters_is_refused_naming_the_export(first_move, tmp_path):
    bare = tmp_path / "bare"
    shutil.copytree(first_move.arms["lean"].copy / "rules", bare / "rules", symlinks=True)

    refusal = _refusal(first_move.arms["lean"].copy, bare)

    assert "export-cursor-rules.py" in refusal


def test_a_moved_rule_with_no_section_to_measure_is_refused(checkout, tmp_path):
    flat = tmp_path / "flat"
    shutil.copytree(checkout / "rules", flat / "rules", symlinks=True)
    (flat / GIT_RULE).write_text("## Git Conventions\n\n- one line\n", encoding="utf-8")

    with pytest.raises(ReachError, match="holds no '###' section"):
        reach.require_reach(declaration.kit(GIT_MOVE), flat, flat, [])


# -- The measure itself -----------------------------------------------------------------------


def test_sections_are_split_at_third_level_headings_and_keep_their_heading_line():
    text = (
        "---\ncore: false\n---\n## Title\n\nintro\n\n### One\n\n- a\n\n### Two\n- b\n## Next\n- c\n"
    )

    assert reach.section_lines(text) == {"One": ("### One", "- a"), "Two": ("### Two", "- b")}


def test_a_section_is_reached_only_when_every_one_of_its_lines_is_carried(tmp_path):
    carried = tmp_path / "carried.md"
    carried.write_text("### One\n- a\n### Two\n- b\n", encoding="utf-8")
    sections = {"One": ("### One", "- a"), "Two": ("### Two", "- b", "- b2")}

    assert reach.reached(sections, [carried]) == {"One"}
