"""The texts and the decision record say what the hook steps now cover.

Every text that declared the gap for merges finished outside `git merge` states the
new coverage (a merge finished by `git commit` after a conflict or `--no-commit`,
and a rebase that brings worktrees in, `git pull --rebase` included) and the one
remaining limit (a squash merge, left to `/merge-worktree` and P14); every
document that enumerates the finalize hooks lists `post-rewrite` and none still
counts three; and one architectural decision record partially supersedes dec-424.

These are text-presence checks: the behaviour they pin is documentary.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISIONS = REPO_ROOT / ".ai-state" / "decisions"
PARTIALLY_SUPERSEDED = "dec-424"


def _flat(text: str) -> str:
    """Prose with comment markers and line breaks folded away."""
    lines = [re.sub(r"^\s*#\s?", "", line) for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines))


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _table_rows(relpath: str, needle: str) -> str:
    return " ".join(
        line for line in _read(relpath).splitlines() if line.startswith("|") and needle in line
    )


def _design_merge_in_row() -> str:
    return _table_rows(".ai-state/DESIGN.md", "merge_worktree_log.py")


def _merge_worktree_command() -> str:
    return _read("commands/merge-worktree.md")


def _finalize_chain_comments() -> str:
    return "\n".join(
        line
        for line in _read("scripts/finalize_chain.sh").splitlines()
        if line.lstrip().startswith("#")
    )


def _merge_in_module_documentation() -> str:
    return ast.get_docstring(ast.parse(_read("scripts/merge_worktree_log.py"))) or ""


def _architecture_rows() -> str:
    return (
        _table_rows("docs/architecture.md", "| Observability log")
        + " "
        + _table_rows("docs/architecture.md", "| Git finalize hook chain")
    )


COVERAGE_TEXTS = {
    "the merge-in row of the design document": _design_merge_in_row,
    "the /merge-worktree command": _merge_worktree_command,
    "the finalize chain's step description": _finalize_chain_comments,
    "the merge-in command's module documentation": _merge_in_module_documentation,
    "the observation-log and hook-chain rows of the architecture guide": _architecture_rows,
}
GAP_STATEMENT = re.compile(
    r"(not covered|does not cover|never sees them|left uncovered)[^.;]{0,300}"
    r"(--no-commit|rebases local commits)"
    r"|(--no-commit|rebases local commits)[^.;]{0,300}(not covered|never sees them|left uncovered)",
    re.IGNORECASE,
)


@pytest.mark.parametrize("text", list(COVERAGE_TEXTS))
def test_each_coverage_text_names_the_merges_the_hook_steps_now_merge_in(text: str) -> None:
    prose = _flat(COVERAGE_TEXTS[text]())

    assert prose, f"{text} was not found"
    assert "--no-commit" in prose, f"{text} does not name a merge finished after --no-commit"
    assert "pull --rebase" in prose, f"{text} does not name git pull --rebase"


@pytest.mark.parametrize("text", list(COVERAGE_TEXTS))
def test_each_coverage_text_names_the_squash_merge_as_the_remaining_limit(text: str) -> None:
    prose = _flat(COVERAGE_TEXTS[text]())

    assert re.search(r"squash", prose, re.IGNORECASE), f"{text} does not name the squash merge"
    assert "P14" in prose, f"{text} does not leave the squash merge to P14"


@pytest.mark.parametrize("text", list(COVERAGE_TEXTS))
def test_no_coverage_text_still_says_the_newly_covered_merges_are_uncovered(text: str) -> None:
    prose = _flat(COVERAGE_TEXTS[text]())

    assert GAP_STATEMENT.search(prose) is None, GAP_STATEMENT.search(prose)


# -- Documents that enumerate the finalize hooks --------------------------------------------


def _phase_four_section() -> str:
    text = _read("skills/onboard-project/references/phases-core.md")
    start = text.index("## §Phase 4")
    return text[start : text.index("\n## ", start + 1)]


def _manifest_example_hooks() -> str:
    text = _read("skills/onboard-project/references/phases-core.md")
    return " ".join(line for line in text.splitlines() if '"hooks"' in line)


HOOK_ENUMERATIONS = {
    "the onboarding Phase 4 section": _phase_four_section,
    "the onboarding manifest example": _manifest_example_hooks,
    "docs/onboarding.md": lambda: _read("docs/onboarding.md"),
    "commands/upgrade-project.md": lambda: _read("commands/upgrade-project.md"),
    "README_DEV.md": lambda: _read("README_DEV.md"),
    "scripts/CLAUDE.md": lambda: _read("scripts/CLAUDE.md"),
    "docs/architecture.md": lambda: _read("docs/architecture.md"),
    "scripts/git-finalize-hook.sh": lambda: _read("scripts/git-finalize-hook.sh"),
    "install_claude.sh": lambda: _read("install_claude.sh"),
    "scripts/install_git_hooks.py": lambda: _read("scripts/install_git_hooks.py"),
    "scripts/upgrade_project_pins.sh": lambda: _read("scripts/upgrade_project_pins.sh"),
}
THREE_FINALIZE_HOOKS = re.compile(
    r"\b(three|3)\s+(finalize[- ]hooks?|finalize-hook symlinks|triggers|git hooks|symlinks"
    r"|near-identical hook scripts)\b|\bthe trio\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("document", list(HOOK_ENUMERATIONS))
def test_each_document_that_lists_the_finalize_hooks_lists_the_rewrite_hook(document: str) -> None:
    text = HOOK_ENUMERATIONS[document]()

    assert "post-rewrite" in text, f"{document} does not list post-rewrite"


@pytest.mark.parametrize("document", list(HOOK_ENUMERATIONS))
def test_no_document_still_counts_three_finalize_hooks(document: str) -> None:
    text = _flat(HOOK_ENUMERATIONS[document]())

    assert THREE_FINALIZE_HOOKS.search(text) is None, THREE_FINALIZE_HOOKS.search(text)


def test_the_onboarding_phase_four_text_says_what_the_rewrite_hook_does_for_merge_in() -> None:
    section = _flat(_phase_four_section())

    assert "post-rewrite" in section
    assert re.search(r"merge-in|merges? in", section, re.IGNORECASE), (
        "Phase 4 says nothing of merge-in"
    )
    assert "rebase" in section


# -- The decision record ---------------------------------------------------------------------


def _frontmatter_and_body(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front) or {}, body


def _records_partially_superseding_dec_424() -> list[tuple[dict, str]]:
    records = [
        _frontmatter_and_body(p)
        for p in [*DECISIONS.glob("[0-9]*.md"), *DECISIONS.glob("drafts/[0-9]*.md")]
    ]
    return [
        (front, body)
        for front, body in records
        if PARTIALLY_SUPERSEDED in (front.get("supersedes_in_part") or [])
    ]


def test_one_architectural_record_partially_supersedes_dec_424_with_its_required_sections() -> None:
    records = _records_partially_superseding_dec_424()

    assert len(records) == 1, f"{len(records)} records partially supersede {PARTIALLY_SUPERSEDED}"
    front, body = records[0]
    assert front.get("category") == "architectural"
    assert "## Prior Decision" in body
    assert "## Disconfirmation" in body


def test_the_record_names_the_fleet_reach_and_the_squash_merge_limit() -> None:
    records = _records_partially_superseding_dec_424()
    assert len(records) == 1, f"{len(records)} records partially supersede {PARTIALLY_SUPERSEDED}"
    body = _flat(records[0][1])

    assert "post-rewrite" in body
    assert "post-commit" in body
    assert re.search(r"pin upgrade|upgrade-project|upgrade_project_pins", body), "no fleet reach"
    assert re.search(r"squash", body, re.IGNORECASE), "the squash-merge limit is not named"


def test_dec_424_links_back_to_the_record_and_stays_accepted() -> None:
    records = _records_partially_superseding_dec_424()
    assert len(records) == 1, f"{len(records)} records partially supersede {PARTIALLY_SUPERSEDED}"
    new_id = records[0][0]["id"]
    (dec_424,) = DECISIONS.glob("424-*.md")

    front, _body = _frontmatter_and_body(dec_424)

    assert front.get("status") == "accepted"
    assert new_id in (front.get("superseded_in_part_by") or [])
