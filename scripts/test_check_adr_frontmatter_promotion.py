"""Tests for check_adr_frontmatter_promotion.py -- finalized-ADR promotion gate.

A finalized ADR at ``.ai-state/decisions/<NNN>-<slug>.md`` must self-identify as
``dec-<NNN>`` and must have left the ``proposed`` lifecycle state. This file is the
gate's canary set (rules/swe/gate-liveness.md: a CODE gate ships proof it *fails*
on a known-bad input, not merely that it passes on the current good state).

Behavioral tests:

1. CANARY: a finalized ADR whose frontmatter ``id`` is still a draft id is flagged,
   with the file, the found id, and the expected id named.
2. CANARY: a finalized ADR still carrying ``status: proposed`` is flagged.
3. A conforming ADR is clean (the no-op control -- without it, a gate that flags
   everything would pass canaries 1 and 2).
4. CANARY: ``--staged`` reads index blobs, so the ``RM`` shape -- rename staged by
   ``git mv`` plus an unstaged content rewrite -- is caught at the commit that would
   ship it. The paired default-mode test is the discriminator: it proves the staged
   canary is detecting the index, not merely re-reading a bad working tree.
5. CANARY: a ``.md`` file under ``.ai-state/decisions/`` that matches neither the
   finalized shape nor a known exemption is reported unclassified rather than
   silently skipped (scope fidelity -- the gate's computed scope must not drift
   below its documented scope).
6. CANARY: the CLI surface exits non-zero on a known-bad tree, zero on a clean one.

Canaries 4 and 5 use a real temporary git repo, exercising actual git plumbing
rather than mocks. Import strategy mirrors scripts/test_check_release_staleness.py,
except the module is loaded lazily per test so that a missing module produces a
per-test failure rather than a collection error.

Pinned interface (negotiable with the implementer, recorded in LEARNINGS.md):

    find_violations(repo_root: Path, *, staged: bool = False) -> list[str]
    main(argv: list[str]) -> int   # 0 clean / 1 violations found
"""

from __future__ import annotations

import functools
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_adr_frontmatter_promotion.py"


@functools.lru_cache(maxsize=1)
def _gate() -> Any:
    """Load the gate module under test, caching it across tests."""
    spec = importlib.util.spec_from_file_location("check_adr_frontmatter_promotion", _SCRIPT_PATH)
    assert spec is not None, f"gate module not importable at {_SCRIPT_PATH}"
    assert spec.loader is not None, f"gate module has no loader at {_SCRIPT_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _exit_code(argv: list[str]) -> int:
    """Run the gate's CLI, tolerating either a returned or a raised exit code."""
    try:
        return int(_gate().main(argv))
    except SystemExit as exc:  # sibling check-scripts differ on this convention
        return int(exc.code or 0)


# -- Fixture builders ---------------------------------------------------------


DRAFT_FRONTMATTER_ID = "dec-draft-abcd1234"  # id-citation-discipline:ignore


def _decisions_dir(root: Path) -> Path:
    path = root / ".ai-state" / "decisions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _adr_text(*, adr_id: str, status: str) -> str:
    return (
        "---\n"
        f"id: {adr_id}\n"
        "title: Some decision\n"
        f"status: {status}\n"
        "category: architectural\n"
        "date: 2026-07-31\n"
        "---\n"
        "\n"
        "## Context\n"
        "\n"
        "Body.\n"
    )


def _write_adr(root: Path, name: str, *, adr_id: str, status: str = "accepted") -> Path:
    path = _decisions_dir(root) / name
    path.write_text(_adr_text(adr_id=adr_id, status=status), encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(root: Path) -> Path:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    return root


@pytest.fixture
def rm_shape_repo(tmp_path: Path) -> Path:
    """A repo reproducing the RM shape finalize leaves behind.

    The draft is committed, rewritten in place with correct finalized frontmatter,
    then ``git mv``-ed. Git stages the rename against the *pre-rewrite* blob, so the
    index holds a promoted ADR that still self-identifies as a draft while the
    working tree is clean.
    """
    repo = _init_repo(tmp_path)
    drafts = _decisions_dir(repo) / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    fragment = drafts / "20260731-2115-user-branch-some-decision.md"
    fragment.write_text(_adr_text(adr_id=DRAFT_FRONTMATTER_ID, status="proposed"), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: add draft ADR")

    fragment.write_text(_adr_text(adr_id="dec-310", status="accepted"), encoding="utf-8")
    _git(
        repo,
        "mv",
        str(fragment.relative_to(repo)),
        ".ai-state/decisions/310-some-decision.md",
    )
    return repo


# -- Tests --------------------------------------------------------------------


def test_flags_finalized_adr_whose_id_is_still_a_draft_id(tmp_path: Path) -> None:
    # CANARY: known-bad input -- 310-*.md self-identifying as an unpromoted draft.
    _write_adr(tmp_path, "310-some-decision.md", adr_id=DRAFT_FRONTMATTER_ID)

    violations = _gate().find_violations(tmp_path)

    report = "\n".join(violations)
    assert violations, "a draft id in a finalized ADR must be flagged"
    assert "310-some-decision.md" in report, report
    assert DRAFT_FRONTMATTER_ID in report, report
    assert "dec-310" in report, report


def test_flags_finalized_adr_whose_status_is_still_proposed(tmp_path: Path) -> None:
    # CANARY: known-bad input -- the lifecycle flip finalize represents never happened.
    _write_adr(tmp_path, "311-other-decision.md", adr_id="dec-311", status="proposed")

    violations = _gate().find_violations(tmp_path)

    report = "\n".join(violations)
    assert violations, "status: proposed in a finalized ADR must be flagged"
    assert "311-other-decision.md" in report, report
    assert "proposed" in report, report


def test_conforming_adr_is_clean(tmp_path: Path) -> None:
    _write_adr(tmp_path, "312-good-decision.md", adr_id="dec-312", status="accepted")

    assert _gate().find_violations(tmp_path) == []


def test_staged_mode_detects_draft_id_present_only_in_the_git_index(
    rm_shape_repo: Path,
) -> None:
    # CANARY: the RM shape -- the working tree is correct, the staged blob is not.
    violations = _gate().find_violations(rm_shape_repo, staged=True)

    report = "\n".join(violations)
    assert violations, "staged mode must read index blobs, not the working tree"
    assert "310-some-decision.md" in report, report
    assert DRAFT_FRONTMATTER_ID in report, report


def test_default_mode_is_clean_when_only_the_index_holds_the_draft_id(
    rm_shape_repo: Path,
) -> None:
    # Discriminator for the canary above: without this, a gate that always read the
    # working tree could still pass the staged canary on a bad working tree.
    assert _gate().find_violations(rm_shape_repo, staged=False) == []


def test_flags_unclassified_file_in_the_decisions_directory(tmp_path: Path) -> None:
    # CANARY: scope fidelity -- an unrecognized name must be reported, not skipped.
    _write_adr(tmp_path, "312-good-decision.md", adr_id="dec-312")
    (_decisions_dir(tmp_path) / "weird-name.md").write_text(
        _adr_text(adr_id="dec-999", status="accepted"), encoding="utf-8"
    )

    violations = _gate().find_violations(tmp_path)

    report = "\n".join(violations)
    assert violations, "an unclassified decisions file must be reported"
    assert "weird-name.md" in report, report


def test_index_claude_and_drafts_are_not_reported_unclassified(tmp_path: Path) -> None:
    decisions = _decisions_dir(tmp_path)
    (decisions / "DECISIONS_INDEX.md").write_text("# Index\n", encoding="utf-8")
    (decisions / "CLAUDE.md").write_text("# Decisions\n", encoding="utf-8")
    drafts = decisions / "drafts"
    drafts.mkdir()
    (drafts / "20260731-2115-user-branch-some-decision.md").write_text(
        _adr_text(adr_id=DRAFT_FRONTMATTER_ID, status="proposed"), encoding="utf-8"
    )

    assert _gate().find_violations(tmp_path) == []


def test_cli_exits_nonzero_when_a_violation_is_present(tmp_path: Path) -> None:
    # CANARY (CLI surface): the exit code is what the pre-commit hook consumes.
    _write_adr(tmp_path, "310-some-decision.md", adr_id=DRAFT_FRONTMATTER_ID)

    assert _exit_code(["--repo-root", str(tmp_path)]) == 1


def test_cli_exits_zero_when_all_adrs_conform(tmp_path: Path) -> None:
    _write_adr(tmp_path, "312-good-decision.md", adr_id="dec-312", status="accepted")

    assert _exit_code(["--repo-root", str(tmp_path)]) == 0
