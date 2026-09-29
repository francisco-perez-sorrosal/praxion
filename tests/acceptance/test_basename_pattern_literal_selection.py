"""Tests that read files by a basename pattern run when a matching file changes.

A Python test that globs `*.md` depends on every Markdown file, though no
import or path names one. A slash-less string literal in a Python pocket
module therefore connects that module to changed files by basename:

- a literal with a wildcard (`*`, `?` or `[`) matches as a glob pattern;
- a literal without one matches only that exact basename;
- a literal made only of `*` and `?` names no file, so a stray asterisk can
  never mark every change as covered.

Everything the literal does not account for still widens exactly as before.
Each scenario builds a single-pocket Python repository and names the changed
files explicitly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.scope_resolver import (
    ScratchRepo,
    new_scratch_repo,
    resolve,
    selected_tests,
    unmapped_paths,
)

PYPROJECT = '[tool.pytest.ini_options]\ntestpaths = ["tests", "pkg"]\n'


def _literal_reader(literal: str) -> str:
    """A test module whose only tie to other files is one string literal."""
    return f'PATTERN = "{literal}"\n\n\ndef test_reads_by_pattern():\n    assert PATTERN\n'


@pytest.fixture
def repo(tmp_path: Path) -> ScratchRepo:
    scratch = new_scratch_repo(tmp_path)
    scratch.write("pyproject.toml", PYPROJECT)
    scratch.write("tests/test_smoke.py", "def test_smoke():\n    assert True\n")
    return scratch


# -- A wildcard literal selects the tests that read by it --------------------


@pytest.mark.parametrize(
    ("literal", "changed"),
    [
        ("*.md", "docs/intro.md"),
        ("*.md", "docs/guide/deep/nested/intro.md"),
        ("report_??.csv", "data/reports/report_07.csv"),
        ("[abc]_case.json", "fixtures/b_case.json"),
    ],
)
def test_a_test_holding_a_wildcard_literal_is_selected_for_a_matching_file(
    repo: ScratchRepo, literal: str, changed: str
) -> None:
    repo.write("tests/test_reads_by_pattern.py", _literal_reader(literal))
    repo.write(changed, "content\n")
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", changed)

    selected = selected_tests(payload)
    assert "tests/test_reads_by_pattern.py" in selected, (
        f"{changed} matches {literal!r} yet its reader was not selected: {payload}"
    )
    reader = selected["tests/test_reads_by_pattern.py"]
    assert reader["via"] == "path-literal"
    assert reader["because"] == changed


def test_a_file_read_only_by_a_wildcard_literal_gets_the_narrow_run(repo: ScratchRepo) -> None:
    repo.write("tests/test_reads_by_pattern.py", _literal_reader("*.md"))
    repo.write("docs/guide/intro.md", "# Intro\n")
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", "docs/guide/intro.md")

    assert "docs/guide/intro.md" not in unmapped_paths(payload), payload["widen"]
    assert payload["decision"] == "selected"


def test_tests_reaching_a_source_module_that_holds_a_wildcard_literal_are_selected(
    repo: ScratchRepo,
) -> None:
    repo.write("pkg/__init__.py")
    repo.write("pkg/doc_index.py", 'DOC_PATTERN = "*.md"\n')
    repo.write(
        "tests/test_doc_index.py",
        "from pkg import doc_index\n\n\ndef test_pattern():\n    assert doc_index.DOC_PATTERN\n",
    )
    repo.write("docs/intro.md", "# Intro\n")
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", "docs/intro.md")

    assert "tests/test_doc_index.py" in selected_tests(payload), payload


# -- Another source never displaces the wildcard reader ----------------------


def _other_reader_by_slash_path(repo: ScratchRepo) -> None:
    repo.write("tests/test_other_reader.py", _literal_reader("docs/guide.md"))


def _other_reader_by_exact_basename(repo: ScratchRepo) -> None:
    repo.write("tests/test_other_reader.py", _literal_reader("guide.md"))


def _other_reader_by_declaration(repo: ScratchRepo) -> None:
    repo.write("tests/test_other_reader.py", "def test_renders():\n    assert True\n")
    repo.write(
        "tests/declared-deps.toml",
        "schema = 1\n\n"
        "[[dep]]\n"
        'paths = ["docs/guide.md"]\n'
        'tests = ["tests/test_other_reader.py"]\n'
        'why = "renders the guide by convention"\n',
    )


@pytest.mark.parametrize(
    "add_other_reader",
    [_other_reader_by_slash_path, _other_reader_by_declaration, _other_reader_by_exact_basename],
    ids=["slash-path-literal", "declared-dependency", "exact-basename-literal"],
)
def test_a_file_mapped_elsewhere_still_selects_its_wildcard_reader(
    repo: ScratchRepo, add_other_reader
) -> None:
    repo.write("tests/test_reads_by_pattern.py", _literal_reader("*.md"))
    repo.write("docs/guide.md", "# Guide\n")
    add_other_reader(repo)
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", "docs/guide.md")

    selected = selected_tests(payload)
    assert {"tests/test_reads_by_pattern.py", "tests/test_other_reader.py"} <= set(selected), (
        f"expected both readers of docs/guide.md, got {sorted(selected)}"
    )


# -- An exact-basename literal matches only that basename --------------------


@pytest.mark.parametrize(
    "changed", ["settings.yaml", "config/settings.yaml", "a/b/c/settings.yaml"]
)
def test_an_exact_basename_literal_selects_its_reader_at_any_depth(
    repo: ScratchRepo, changed: str
) -> None:
    repo.write("tests/test_reads_settings.py", _literal_reader("settings.yaml"))
    repo.write(changed, "key: 1\n")
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", changed)

    assert "tests/test_reads_settings.py" in selected_tests(payload), payload
    assert changed not in unmapped_paths(payload)


@pytest.mark.parametrize(
    "changed",
    ["config/app-settings.yaml", "config/settings.yaml.bak", "config/settings.yaml5"],
)
def test_an_exact_basename_literal_does_not_account_for_a_merely_similar_name(
    repo: ScratchRepo, changed: str
) -> None:
    repo.write("tests/test_reads_settings.py", _literal_reader("settings.yaml"))
    repo.write(changed, "key: 1\n")
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", changed)

    assert changed in unmapped_paths(payload), (
        f"{changed} is only similar to 'settings.yaml' yet did not widen: {payload}"
    )
    assert payload["decision"] == "widened"


# -- A literal made only of wildcards names no file ---------------------------


@pytest.mark.parametrize("literal", ["*", "**", "?", "?*", "***"])
def test_a_literal_made_only_of_wildcards_leaves_an_unmapped_change_widened(
    repo: ScratchRepo, literal: str
) -> None:
    repo.write("tests/test_separator.py", _literal_reader(literal))
    repo.write("data/sample.txt", "rows\n")
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", "data/sample.txt")

    assert "data/sample.txt" in unmapped_paths(payload), (
        f"the literal {literal!r} switched off the unmapped-path backstop: {payload}"
    )
    assert payload["decision"] == "widened"


# -- No other narrowing ------------------------------------------------------


@pytest.mark.parametrize("changed", ["docs/notes.txt", "docs/notes.mdx", "docs/intro.md.bak"])
def test_a_file_the_wildcard_does_not_match_still_widens(repo: ScratchRepo, changed: str) -> None:
    repo.write("tests/test_reads_by_pattern.py", _literal_reader("*.md"))
    repo.write(changed, "content\n")
    repo.commit_all("seed")

    payload = resolve(repo, "--changed", changed)

    assert changed in unmapped_paths(payload), payload
    assert payload["decision"] == "widened"


def test_a_deleted_python_source_still_selects_its_surviving_readers(repo: ScratchRepo) -> None:
    repo.write("pkg/__init__.py")
    repo.write("pkg/legacy.py", "value = 1\n")
    repo.write("tests/test_reads_legacy.py", _literal_reader("pkg/legacy.py"))
    repo.commit_all("seed")
    repo.git("rm", "-q", "pkg/legacy.py")

    payload = resolve(repo)

    assert payload["decision"] == "selected", payload
    assert "tests/test_reads_legacy.py" in selected_tests(payload)
