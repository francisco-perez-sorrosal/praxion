"""Tests for the parent commit's side of a move in kernel_ledger_history.py, beyond the ledger.

The eligible roles pinned in `scripts/kernel_eligibility.py`, the adoption records as written and
the agent definitions, all read at the parent a commit is judged from. Self-contained, like
`test_kernel_ledger.py`: it imports no checker, which reads the repository's own files and so
cannot run where the mutation sensor relocates a test file. Every case builds its own repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_ledger_history as kh  # noqa: E402
import kernel_model as km  # noqa: E402

COMMITTED = "2026-10-13T12:00:00+00:00"
TRIAL_LEDGER = "version: 1\nroles:\n  researcher: {status: trial, runs: []}\n"
EMPTY_LEDGER = "version: 1\nroles: {}\n"


def commit_all(root: Path, at: str = COMMITTED) -> None:
    """Commit everything under `root`, a repository of its own, at the moment `at`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_DATE=at, GIT_COMMITTER_DATE=at)
    identity = ["-c", "user.name=Probe", "-c", "user.email=probe@example.invalid"]
    steps = (["init", "-q"], ["add", "-A"], [*identity, "commit", "-q", "--no-verify", "-m", "x"])
    for step in steps:
        subprocess.run(
            ["git", *step], cwd=root, env=env, check=True, capture_output=True, timeout=60
        )


def write(root: Path, text: str) -> None:
    write_file(root, km.LEDGER_PATH, text)


def commit_ledger(root: Path, text: str) -> None:
    write(root, text)
    commit_all(root)


# -- What the parent commit held besides the ledger: the pin, the records, the definitions --------

PIN = "scripts/kernel_eligibility.py"
FIRST_PIN = ("researcher", "verifier")
SECOND_PIN = ("researcher", "verifier", "skill-genesis")


def write_file(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


def write_pin(root: Path, roles: tuple[str, ...]) -> None:
    write_file(root, PIN, f"ELIGIBLE_ROLES = {roles!r}\n")


def flip_read(root: Path, *agents: str) -> kh.ParentFlip:
    read = kh.parent_flip(root, agents)
    assert read is not None, "the parent commit is in this repository"
    return read


def two_commits(root: Path) -> None:
    """HEAD^ pins the first list and HEAD the second; the tree is HEAD's."""
    write_pin(root, FIRST_PIN)
    commit_all(root)
    write_pin(root, SECOND_PIN)
    commit_all(root, at="2026-10-14T08:00:00+00:00")


def test_a_tree_that_is_heads_has_its_own_move_read_from_the_first_parent(tmp_path: Path) -> None:
    two_commits(tmp_path)

    assert flip_read(tmp_path).eligible == FIRST_PIN


@pytest.mark.parametrize(
    "dirty",
    [
        lambda root: write_pin(root, ("researcher",)),
        lambda root: write_file(root, km.LEDGER_PATH, TRIAL_LEDGER),
        lambda root: write_file(root, "agents/researcher.md", "---\nname: researcher\n---\n"),
    ],
    ids=["the pin", "the ledger", "a definition"],
)
def test_a_tree_that_differs_from_head_in_a_move_input_is_a_commit_built_on_head(
    tmp_path: Path, dirty
) -> None:
    two_commits(tmp_path)

    dirty(tmp_path)

    assert flip_read(tmp_path).eligible == SECOND_PIN


def test_a_tree_that_differs_from_head_in_nothing_a_move_reads_is_still_heads_own(
    tmp_path: Path,
) -> None:
    two_commits(tmp_path)

    write_file(tmp_path, "README.probe", "unrelated\n")

    assert flip_read(tmp_path).eligible == FIRST_PIN


def test_the_parent_commits_records_are_read_as_written(tmp_path: Path) -> None:
    write_pin(tmp_path, FIRST_PIN)
    commit_ledger(tmp_path, TRIAL_LEDGER)
    write(tmp_path, EMPTY_LEDGER)

    assert flip_read(tmp_path).records == {"researcher": {"status": "trial", "runs": []}}


def test_a_parent_commit_without_a_ledger_holds_no_records(tmp_path: Path) -> None:
    write_pin(tmp_path, FIRST_PIN)
    commit_all(tmp_path)
    write_pin(tmp_path, SECOND_PIN)

    assert flip_read(tmp_path).records == {}


def test_the_parent_commits_definitions_are_read_for_the_agents_asked_after(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "agents/researcher.md", "---\nname: researcher\n---\nthen\n")
    commit_all(tmp_path)
    write_file(tmp_path, "agents/researcher.md", "---\nname: researcher\n---\nnow\n")
    write_file(tmp_path, "agents/verifier.md", "---\nname: verifier\n---\nnew\n")

    read = flip_read(tmp_path, "researcher", "verifier")

    assert read.definitions == {"researcher": "---\nname: researcher\n---\nthen\n"}


def test_a_parent_commit_pinning_nothing_is_held_to_the_list_its_ledger_carried(
    tmp_path: Path,
) -> None:
    commit_ledger(tmp_path, "version: 1\neligible: [researcher, 7, verifier]\nroles: {}\n")
    write(tmp_path, EMPTY_LEDGER)

    assert flip_read(tmp_path).eligible == ("researcher", "verifier")


@pytest.mark.parametrize("ledger", [EMPTY_LEDGER, None], ids=["a ledger without a list", "none"])
def test_a_parent_commit_that_lists_no_eligible_roles_anywhere_is_not_yet_pinned(
    tmp_path: Path, ledger: str | None
) -> None:
    write_file(tmp_path, "unrelated.txt", "x")
    if ledger is not None:
        write(tmp_path, ledger)
    commit_all(tmp_path)
    write_file(tmp_path, "agents/researcher.md", "---\nname: researcher\n---\n")

    assert flip_read(tmp_path).eligible == kh.NotYetPinned()


def test_a_pin_in_the_parent_commit_outranks_the_list_its_ledger_carried(tmp_path: Path) -> None:
    write_pin(tmp_path, FIRST_PIN)
    commit_ledger(tmp_path, "version: 1\neligible: [sentinel]\nroles: {}\n")
    write_pin(tmp_path, SECOND_PIN)

    assert flip_read(tmp_path).eligible == FIRST_PIN


def test_a_directory_with_no_repository_has_no_parent_to_read(tmp_path: Path) -> None:
    assert kh.parent_flip(tmp_path, ["researcher"]) is None


def test_a_shallow_clone_without_the_parent_commit_has_no_parent_to_read(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    two_commits(source)
    clone = tmp_path / "shallow"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", f"file://{source}", str(clone)],
        check=True,
        capture_output=True,
        env=env,
        timeout=60,
    )

    assert kh.parent_flip(clone, []) is None


def test_a_parent_commit_whose_ledger_is_not_yaml_is_refused_naming_its_revision(
    tmp_path: Path,
) -> None:
    commit_ledger(tmp_path, "roles: [unclosed")
    write(tmp_path, EMPTY_LEDGER)

    with pytest.raises(km.KernelModelError, match=f"{km.LEDGER_PATH} at HEAD: not valid YAML"):
        kh.parent_flip(tmp_path, [])


def test_a_parent_commit_whose_pin_binds_no_tuple_is_refused_naming_it(tmp_path: Path) -> None:
    write_file(tmp_path, PIN, "ELIGIBLE_ROLES = ['researcher']\n")
    commit_all(tmp_path)
    write_pin(tmp_path, FIRST_PIN)

    with pytest.raises(km.KernelModelError, match=f"{PIN} at HEAD: ELIGIBLE_ROLES is not a tuple"):
        kh.parent_flip(tmp_path, [])


@pytest.mark.parametrize(
    "source",
    ["OTHER = ('researcher',)\n", "ELIGIBLE_ROLES = ('a'\n", "ELIGIBLE_ROLES = (os.name,)\n"],
    ids=["unbound", "not python", "not a literal"],
)
def test_a_pin_that_binds_no_literal_is_refused_naming_where(source: str) -> None:
    with pytest.raises(km.KernelModelError, match=f"{PIN}: binds no literal ELIGIBLE_ROLES"):
        kh.pinned_roles(source, PIN)


@pytest.mark.parametrize("source", ["ELIGIBLE_ROLES = ['a']\n", "ELIGIBLE_ROLES = (1, 'a')\n"])
def test_a_pin_that_is_not_a_tuple_of_role_names_is_refused(source: str) -> None:
    with pytest.raises(km.KernelModelError, match="is not a tuple of role names"):
        kh.pinned_roles(source, PIN)


def test_a_pin_is_read_without_running_it() -> None:
    assert kh.pinned_roles('import os\nOTHER = 1\nELIGIBLE_ROLES = ("a", "b")\n', PIN) == ("a", "b")


def test_the_records_of_a_ledger_without_any_are_none() -> None:
    assert kh.written_records({"version": 1}) == {}
    assert kh.written_records({"roles": None}) == {}


def test_records_that_are_not_a_mapping_are_refused_naming_roles() -> None:
    with pytest.raises(km.KernelModelError, match="^roles must be a mapping"):
        kh.written_records({"roles": ["researcher"]})


def test_no_ledger_text_is_an_empty_ledger() -> None:
    assert kh.ledger_mapping(None, km.LEDGER_PATH) == {}
