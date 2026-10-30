"""The git-conventions kit's task list and fixtures: distinct, balanced, free of the rule's words,
and each a repository a scripted commit succeeds in."""

from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence.moves import checks_git, kit_git
from praxion_evals.adherence.moves.declaration import kit
from praxion_evals.adherence.moves.model import MoveDeclaration, OnlyKind
from praxion_evals.adherence.moves.tasks import MoveTask, screen, target_with_slack

SEED = 7
DECLARATION = kit("git-conventions")
MANAGED_ONLY = replace(DECLARATION, fixture_scope=OnlyKind("managed"))
PHRASES = [p for check in DECLARATION.checks.checks for p in check.phrases]


def the_tasks(declaration: MoveDeclaration = DECLARATION, seed: int = SEED) -> tuple[MoveTask, ...]:
    return kit_git.tasks(declaration, seed)


def first_task_of(fixture: kit_git.Fixture) -> MoveTask:
    return next(t for t in kit_git.candidates() if t.fixture == fixture.name)


def paths(files: kit_git.Files) -> set[str]:
    return {path for path, _ in files}


def untracked(root: Path) -> set[str]:
    return set(git(root, "ls-files", "--others", "--exclude-standard").split())


def git(root: Path, *args: str, home: Path | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE"))}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    if home is not None:
        env["HOME"] = str(home)
    done = subprocess.run(
        ["git", "-C", str(root), *args], env=env, capture_output=True, text=True, check=True
    )
    return done.stdout


def test_the_list_holds_the_default_target_plus_slack_of_distinct_tasks() -> None:
    tasks = the_tasks()

    assert len(tasks) == target_with_slack()
    assert len({t.task_id for t in tasks}) == len(tasks)
    assert len({(t.fixture, t.wording) for t in tasks}) == len(tasks)


def test_each_fixture_kind_holds_a_third_of_the_list() -> None:
    kinds = [t.fixture_kind for t in the_tasks()]

    assert min(kinds.count("managed"), kinds.count("unmanaged")) * 3 >= len(kinds)


def test_a_managed_only_declaration_draws_every_task_from_the_managed_kind() -> None:
    assert {t.fixture_kind for t in the_tasks(MANAGED_ONLY)} == {"managed"}


def test_every_candidate_is_distinct_and_the_list_is_drawn_from_them() -> None:
    pool = kit_git.candidates()

    assert len({(t.fixture, t.wording) for t in pool}) == len(pool)
    assert set(the_tasks()) <= set(pool)


def test_the_same_seed_draws_the_same_list_and_another_seed_another_order() -> None:
    ids = [t.task_id for t in the_tasks()]

    assert [t.task_id for t in the_tasks()] == ids
    assert [t.task_id for t in the_tasks(seed=SEED + 1)] != ids


def test_no_wording_carries_a_declared_phrase_or_invokes_a_command() -> None:
    assert [
        (t.task_id, screen(t.wording, PHRASES)) for t in the_tasks() if screen(t.wording, PHRASES)
    ] == []


def test_every_wording_names_every_file_its_task_names() -> None:
    assert all(f in t.wording for t in the_tasks() for f in t.named_files)


def test_every_wording_describes_its_fixtures_work() -> None:
    summaries = {f.name: f.summary for f in kit_git.FIXTURES}

    assert [t.task_id for t in kit_git.candidates() if summaries[t.fixture] not in t.wording] == []


def test_every_fixtures_history_holds_a_subject_the_message_check_would_fail() -> None:
    def breaks_the_form(subject: str) -> bool:
        return len(subject) > checks_git.MAX_SUBJECT_CHARACTERS or subject.endswith(".")

    assert [f.name for f in kit_git.FIXTURES if not any(map(breaks_the_form, f.history))] == []


def test_most_fixtures_name_a_tracked_file_the_work_changed() -> None:
    changed = [f.name for f in kit_git.FIXTURES if f.before]

    assert len(changed) * 2 > len(kit_git.FIXTURES)


def test_some_fixtures_name_several_files_and_some_leave_an_unnamed_file_beside_a_named_one() -> (
    None
):
    several = [f.name for f in kit_git.FIXTURES if len(f.named) >= 3]
    beside = [
        f.name
        for f in kit_git.FIXTURES
        if any(
            Path(u).parent != Path(".")
            and Path(u).parent in {Path(n).parent for n in f.named_paths}
            for u in paths(f.unnamed)
        )
    ]

    assert len(several) >= 2
    assert len(beside) >= 2


def test_some_task_plants_a_credential_in_a_file_its_request_does_not_name() -> None:
    planted = [t for t in the_tasks() if t.planted_credential]

    assert planted
    assert all(t.planted_credential not in t.wording for t in planted)


@pytest.mark.parametrize("fixture", kit_git.FIXTURES, ids=lambda f: f.name)
def test_a_fixture_holds_the_named_files_and_untracked_files_the_request_does_not_name(
    fixture: kit_git.Fixture, tmp_path: Path
) -> None:
    task = first_task_of(fixture)

    root = kit_git.build_fixture(DECLARATION, task, tmp_path / "repo")

    assert all((root / path).is_file() for path in task.named_files)
    assert untracked(root) == (paths(fixture.named) - paths(fixture.before)) | paths(
        fixture.unnamed
    )
    assert not set(task.named_files) & paths(fixture.unnamed)
    assert task.planted_credential is None or task.planted_credential in untracked(root)


@pytest.mark.parametrize("fixture", kit_git.FIXTURES, ids=lambda f: f.name)
def test_a_fixture_is_its_own_history_up_to_the_baseline_ref_plus_uncommitted_work(
    fixture: kit_git.Fixture, tmp_path: Path
) -> None:
    root = kit_git.build_fixture(DECLARATION, first_task_of(fixture), tmp_path / "repo")

    assert git(root, "log", "--reverse", "--format=%s").splitlines() == list(fixture.history)
    assert git(root, "rev-parse", checks_git.BASELINE_REF) == git(root, "rev-parse", "HEAD")
    assert set(git(root, "diff", "--name-only").split()) == paths(fixture.before) | {
        kit_git.TRACKED_NOTE
    }


def test_a_managed_fixture_carries_a_state_directory_and_the_shipped_blocks_but_no_sidecar_block(
    tmp_path: Path,
) -> None:
    managed = next(f for f in kit_git.FIXTURES if f.kind == "managed")

    root = kit_git.build_fixture(DECLARATION, first_task_of(managed), tmp_path / "repo")

    claude_md = (root / "CLAUDE.md").read_text(encoding="utf-8")
    shipped = {
        p.name: p.read_text(encoding="utf-8").strip() for p in kit_git.CANONICAL_BLOCKS.glob("*.md")
    }
    assert (root / ".ai-state").is_dir()
    assert all(
        text in claude_md for name, text in shipped.items() if name != "sidecar-placement.md"
    )
    assert shipped["sidecar-placement.md"] not in claude_md


def test_an_unmanaged_fixture_carries_no_state_directory_and_no_project_instructions(
    tmp_path: Path,
) -> None:
    unmanaged = next(f for f in kit_git.FIXTURES if f.kind == "unmanaged")

    root = kit_git.build_fixture(DECLARATION, first_task_of(unmanaged), tmp_path / "repo")

    assert not (root / ".ai-state").exists()
    assert not (root / "CLAUDE.md").exists()


@pytest.mark.parametrize("fixture", kit_git.FIXTURES, ids=lambda f: f.name)
def test_a_scripted_commit_of_the_named_files_succeeds_and_grades_conforming(
    fixture: kit_git.Fixture, tmp_path: Path
) -> None:
    task = first_task_of(fixture)
    root = kit_git.build_fixture(DECLARATION, task, tmp_path / "repo")
    home = tmp_path / "sandbox-home"
    home.mkdir()

    git(root, "add", "--", *task.named_files, home=home)
    git(root, "commit", "-m", "Commit the named files", home=home)

    assert git(root, "log", "-1", "--format=%ae", home=home) == git(root, "config", "user.email")
    for check in DECLARATION.checks.checks:
        assert checks_git.grade(DECLARATION, check.name, root, task.named_files).outcome == "passed"


def test_a_commit_of_everything_fails_the_staging_check(tmp_path: Path) -> None:
    task = the_tasks()[0]
    root = kit_git.build_fixture(DECLARATION, task, tmp_path / "repo")

    git(root, "add", "--all")
    git(root, "commit", "-m", "Commit everything")

    grade = checks_git.grade(DECLARATION, checks_git.STAGING_BY_NAME, root, task.named_files)
    assert grade.failed_parts == (checks_git.UNNAMED_FILE_COMMITTED,)


@pytest.mark.parametrize("fixture", [f for f in kit_git.FIXTURES if f.before], ids=lambda f: f.name)
def test_a_commit_of_every_tracked_change_takes_the_unnamed_note_along(
    fixture: kit_git.Fixture, tmp_path: Path
) -> None:
    task = first_task_of(fixture)
    root = kit_git.build_fixture(DECLARATION, task, tmp_path / "repo")

    git(root, "commit", "-a", "-m", "Commit the tracked changes")

    grade = checks_git.grade(DECLARATION, checks_git.STAGING_BY_NAME, root, task.named_files)
    assert checks_git.UNNAMED_FILE_COMMITTED in grade.failed_parts


def test_a_fixture_is_not_built_over_a_directory_that_holds_something(tmp_path: Path) -> None:
    (tmp_path / "taken.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="is not empty"):
        kit_git.build_fixture(DECLARATION, the_tasks()[0], tmp_path)


def test_a_fixture_of_a_kind_the_declaration_does_not_admit_is_refused(tmp_path: Path) -> None:
    unmanaged = next(t for t in the_tasks() if t.fixture_kind == "unmanaged")

    with pytest.raises(ValueError, match="does not admit the unmanaged"):
        kit_git.build_fixture(MANAGED_ONLY, unmanaged, tmp_path / "repo")


def test_a_task_of_no_fixture_here_is_refused(tmp_path: Path) -> None:
    stranger = replace(the_tasks()[0], fixture="no-such-fixture")

    with pytest.raises(ValueError, match="no fixture named 'no-such-fixture'"):
        kit_git.build_fixture(DECLARATION, stranger, tmp_path / "repo")
