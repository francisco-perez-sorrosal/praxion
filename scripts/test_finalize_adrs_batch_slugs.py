"""A batch of drafts finalizes under the names its plan announced.

Two ways a hyphenated authoring branch used to leak into a finalized record's
file name, both seen on one merge: a draft whose frontmatter names the branch
as git prints it (`feat/small-debt`, with a slash) had that field ignored, and
the last draft of a batch was parsed a second time after its siblings had
already left `drafts/`, so nothing was left to tell its branch from its slug.
The run then stopped on the file name it had planned and never regenerated
the index.

The tests drive the real entry point over a temporary, non-git state
directory, so the plain-rename path runs and no git call is made.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import finalize_adrs
import pytest

AUTHOR = "alice"
BRANCH_AS_GIT_PRINTS_IT = "feat/small-debt"
BRANCH_SLUG = "feat-small-debt"
FIRST_SLUG = "generated-names"
LAST_SLUG = "follow-up-record"


@pytest.fixture
def state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the finalize module at a temporary state directory, as `main` does."""
    decisions = tmp_path / ".ai-state" / "decisions"
    drafts = decisions / "drafts"
    drafts.mkdir(parents=True)
    for name, value in (
        ("REPO_ROOT", tmp_path),
        ("DECISIONS_DIR", decisions),
        ("DRAFTS_DIR", drafts),
        ("LOCK_PATH", drafts / ".finalize.lock"),
        ("STATE_GIT_ROOT", tmp_path),
    ):
        monkeypatch.setattr(finalize_adrs, name, value)
    # Finalize runs after the merge, on the default branch, so neither hint
    # names the authoring branch.
    monkeypatch.setattr(finalize_adrs, "_current_git_user_slug", lambda: AUTHOR)
    monkeypatch.setattr(finalize_adrs, "_current_git_branch_slug", lambda: "main")
    return tmp_path


def _write_draft(state_root: Path, minute: str, slug: str, branch_field: str | None) -> Path:
    name = f"20261112-01{minute}-{AUTHOR}-{BRANCH_SLUG}-{slug}.md"
    draft_id = "dec-draft-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    branch_line = "" if branch_field is None else f"branch: {branch_field}\n"
    path = state_root / ".ai-state" / "decisions" / "drafts" / name
    path.write_text(
        "---\n"
        f"id: {draft_id}\n"
        f"title: {slug}\n"
        "status: proposed\n"
        "category: architectural\n"
        "date: 2026-11-12\n"
        f"summary: a draft about {slug}\n"
        "tags: [test]\n"
        "made_by: agent\n"
        f"{branch_line}"
        "---\n\n## Context\n\nA draft.\n",
        encoding="utf-8",
    )
    return path


def _finalized_names(state_root: Path) -> list[str]:
    decisions = state_root / ".ai-state" / "decisions"
    return sorted(p.name for p in decisions.glob("[0-9][0-9][0-9]-*.md"))


@pytest.mark.parametrize(
    "branch_field",
    [BRANCH_AS_GIT_PRINTS_IT, f'"{BRANCH_AS_GIT_PRINTS_IT}"', BRANCH_SLUG, "Feat/Small-Debt"],
)
def test_a_lone_draft_takes_its_branch_from_the_frontmatter_however_it_is_spelled(
    state_root: Path, branch_field: str
) -> None:
    draft = _write_draft(state_root, "02", LAST_SLUG, branch_field)

    _, user, branch, slug = finalize_adrs.parse_fragment_filename(draft)

    assert (user, branch, slug) == (AUTHOR, BRANCH_SLUG, LAST_SLUG)


def test_a_frontmatter_branch_the_file_name_does_not_carry_is_not_trusted(
    state_root: Path,
) -> None:
    _write_draft(state_root, "01", FIRST_SLUG, "feat/renamed-since")
    draft = _write_draft(state_root, "02", LAST_SLUG, "feat/renamed-since")

    _, _, branch, slug = finalize_adrs.parse_fragment_filename(draft)

    assert (branch, slug) == (BRANCH_SLUG, LAST_SLUG)


@pytest.mark.parametrize("branch_field", [None, BRANCH_AS_GIT_PRINTS_IT])
def test_every_draft_of_a_batch_is_finalized_under_the_name_its_plan_announced(
    state_root: Path, branch_field: str | None
) -> None:
    drafts = [
        _write_draft(state_root, "01", FIRST_SLUG, branch_field),
        _write_draft(state_root, "02", LAST_SLUG, branch_field),
    ]
    planned = [plan.new_path.name for plan in finalize_adrs.build_promotion_plan(drafts)]

    exit_code = finalize_adrs._run("all", None, dry_run=False)

    assert planned == [f"001-{FIRST_SLUG}.md", f"002-{LAST_SLUG}.md"]
    assert _finalized_names(state_root) == planned
    assert exit_code == 0


def test_a_finished_batch_lists_every_record_in_the_index(state_root: Path) -> None:
    _write_draft(state_root, "01", FIRST_SLUG, None)
    _write_draft(state_root, "02", LAST_SLUG, None)

    finalize_adrs._run("all", None, dry_run=False)

    index = (state_root / ".ai-state" / "decisions" / "DECISIONS_INDEX.md").read_text(
        encoding="utf-8"
    )
    listed = [record for record in ("dec-001", "dec-002") if record in index]
    assert listed == ["dec-001", "dec-002"]
