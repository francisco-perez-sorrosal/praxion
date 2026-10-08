"""Tests for the goal iteration's shell edges: the scope restore, the whole-tree patch and the
headless worker's file (``scripts/_step_loop_io.py`` and ``scripts/_step_loop_files.py``).

The git half runs real ``git`` in scratch repositories built here; the file half runs on real
files in ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_files as files  # noqa: E402
from _git_runner import run_git  # noqa: E402
from _step_loop_files import NoWorkerResult, WorkerEnd  # noqa: E402
from _step_loop_io import OutsideRepoError, restore_paths, tree_patch  # noqa: E402

REQUEST = "s7-a2-implement"
SCOPE = ["src"]
BASE_FILES = {
    "src/one.py": "one = 1\n",
    "src/two.py": "two = 1\n",
    "outside.py": "outside = 1\n",
    "keep.txt": "keep\n",
}
RESULT_OBJECT = {
    "type": "result",
    "subtype": "success",
    "num_turns": 4,
    "session_id": "6b1f0c2e",
    "total_cost_usd": 0.25,
    "permission_denials": [{"tool_name": "Bash"}, {"tool_name": "Edit"}],
    "result": "All done.",
}


def git(repo: Path, *args: str) -> str:
    done = run_git(repo, *args)
    assert done.returncode == 0, done.stderr
    return done.stdout


def write(repo: Path, rel: str, text: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def status(repo: Path) -> str:
    return git(repo, "status", "--porcelain=v1", "--untracked-files=all")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for key, value in {"user.name": "Tester", "user.email": "t@example.invalid"}.items():
        git(root, "config", key, value)
    git(root, "config", "commit.gpgsign", "false")
    for rel, text in BASE_FILES.items():
        write(root, rel, text)
    git(root, "add", "--all")
    git(root, "commit", "-q", "-m", "base")
    return root


# --- restore_paths ------------------------------------------------------------------------


def test_restore_returns_a_modified_tracked_file_to_head(repo: Path) -> None:
    write(repo, "src/one.py", "one = 2\n")

    restore_paths(repo, SCOPE)

    assert (repo / "src/one.py").read_text() == BASE_FILES["src/one.py"]
    assert status(repo) == ""


def test_restore_removes_an_untracked_file_in_the_scope(repo: Path) -> None:
    write(repo, "src/fresh.py", "fresh = 1\n")

    restore_paths(repo, SCOPE)

    assert not (repo / "src/fresh.py").exists()


def test_restore_brings_back_a_deleted_tracked_file(repo: Path) -> None:
    (repo / "src/two.py").unlink()

    restore_paths(repo, SCOPE)

    assert (repo / "src/two.py").read_text() == BASE_FILES["src/two.py"]


def test_restore_undoes_a_staged_edit_and_a_staged_new_file(repo: Path) -> None:
    write(repo, "src/one.py", "one = 3\n")
    write(repo, "src/staged_new.py", "new = 1\n")
    git(repo, "add", "src/one.py", "src/staged_new.py")

    restore_paths(repo, SCOPE)

    assert status(repo) == ""
    assert not (repo / "src/staged_new.py").exists()


def test_restore_leaves_a_modified_file_outside_the_scope_alone(repo: Path) -> None:
    write(repo, "outside.py", "outside = 2\n")
    write(repo, "src/one.py", "one = 2\n")

    restore_paths(repo, SCOPE)

    assert (repo / "outside.py").read_text() == "outside = 2\n"
    assert status(repo) == " M outside.py\n"


def test_restore_leaves_an_untracked_file_outside_the_scope_alone(repo: Path) -> None:
    write(repo, "stray.txt", "stray\n")
    write(repo, "src/fresh.py", "fresh = 1\n")

    restore_paths(repo, SCOPE)

    assert (repo / "stray.txt").read_text() == "stray\n"
    assert status(repo) == "?? stray.txt\n"


def test_restore_leaves_a_staged_file_outside_the_scope_staged(repo: Path) -> None:
    write(repo, "keep.txt", "keep, staged\n")
    git(repo, "add", "keep.txt")

    restore_paths(repo, SCOPE)

    assert status(repo) == "M  keep.txt\n"


def test_restore_removes_the_directories_an_untracked_package_leaves_empty(repo: Path) -> None:
    write(repo, "src/newpkg/__init__.py", "")
    write(repo, "src/newpkg/deep/mod.py", "mod = 1\n")

    restore_paths(repo, SCOPE)

    assert sorted(path.name for path in (repo / "src").iterdir()) == ["one.py", "two.py"]


def test_restore_keeps_a_directory_that_still_holds_a_file_it_did_not_remove(repo: Path) -> None:
    write(repo, "src/newpkg/mod.py", "mod = 1\n")
    write(repo, "src/newpkg/other.py", "other = 1\n")

    restore_paths(repo, ["src/newpkg/mod.py"])

    assert sorted(path.name for path in (repo / "src/newpkg").iterdir()) == ["other.py"]


def test_restore_accepts_single_files_and_names_what_it_acted_on(repo: Path) -> None:
    write(repo, "src/one.py", "one = 2\n")
    write(repo, "src/two.py", "two = 2\n")

    acted = restore_paths(repo, ["src/one.py"])

    assert acted == ("src/one.py",)
    assert status(repo) == " M src/two.py\n"


def test_restore_over_an_unchanged_scope_acts_on_nothing(repo: Path) -> None:
    assert restore_paths(repo, SCOPE) == ()
    assert status(repo) == ""


@pytest.mark.parametrize(
    "refused",
    [
        "../elsewhere.py",
        "src/../../elsewhere.py",
        "/etc/hosts",
        ".git/config",
        ".git",
        ".",
        ".GIT/x",
    ],
)
def test_restore_refuses_a_path_it_may_not_touch_and_touches_nothing(
    repo: Path, refused: str
) -> None:
    write(repo, "src/one.py", "one = 2\n")

    with pytest.raises(OutsideRepoError):
        restore_paths(repo, ["src/one.py", refused])

    assert (repo / "src/one.py").read_text() == "one = 2\n"


# --- tree_patch ---------------------------------------------------------------------------


def test_the_patch_holds_a_modified_tracked_file_and_an_untracked_one(repo: Path) -> None:
    write(repo, "src/one.py", "one = 2\n")
    write(repo, "src/fresh.py", "fresh = 1\n")

    patch = tree_patch(repo)

    assert "+one = 2" in patch
    assert "+fresh = 1" in patch
    assert "b/src/fresh.py" in patch


def test_the_patch_holds_a_staged_edit_a_deletion_and_an_empty_new_file(repo: Path) -> None:
    write(repo, "src/one.py", "one = 4\n")
    git(repo, "add", "src/one.py")
    (repo / "src/two.py").unlink()
    write(repo, "src/empty.py", "")

    patch = tree_patch(repo)

    assert "+one = 4" in patch
    assert "deleted file mode" in patch
    assert "b/src/empty.py" in patch


def test_the_patch_leaves_out_everything_under_the_scratch_directory(repo: Path) -> None:
    write(repo, ".ai-work/slug/WIP.md", "untracked scratch\n")
    write(repo, "src/one.py", "one = 2\n")

    patch = tree_patch(repo)

    assert ".ai-work" not in patch
    assert "+one = 2" in patch


def test_the_patch_leaves_the_index_as_it_found_it(repo: Path) -> None:
    write(repo, "src/one.py", "one = 2\n")
    git(repo, "add", "src/one.py")
    write(repo, "src/two.py", "two = 2\n")
    write(repo, "src/fresh.py", "fresh = 1\n")
    before = (status(repo), git(repo, "diff", "--cached", "--raw"))

    tree_patch(repo)

    assert (status(repo), git(repo, "diff", "--cached", "--raw")) == before


def test_a_clean_tree_has_an_empty_patch(repo: Path) -> None:
    assert tree_patch(repo) == ""


def test_applying_the_patch_after_a_restore_brings_the_iteration_back(repo: Path) -> None:
    write(repo, "src/one.py", "one = 2\n")
    write(repo, "src/fresh.py", "fresh = 1\n")
    (repo / "src/two.py").unlink()
    patch = tree_patch(repo)
    restore_paths(repo, SCOPE)
    (repo / "iteration.patch").write_text(patch)

    git(repo, "apply", "iteration.patch")

    assert (repo / "src/one.py").read_text() == "one = 2\n"
    assert (repo / "src/fresh.py").read_text() == "fresh = 1\n"
    assert not (repo / "src/two.py").exists()


def carry_back(repo: Path, task_dir: Path) -> None:
    """Patch the tree, write the record, restore the scope, then apply the record."""
    path = files.write_iteration_patch(task_dir, REQUEST, tree_patch(repo))
    restore_paths(repo, SCOPE)
    git(repo, "apply", "--whitespace=nowarn", str(path))


def test_a_crlf_file_and_a_latin_1_file_come_back_byte_for_byte(repo: Path, tmp_path: Path) -> None:
    (repo / "src/crlf.txt").write_bytes(b"one\r\ntwo\r\n")
    (repo / "src/latin.txt").write_bytes("caf\xe9\n".encode("latin-1"))
    git(repo, "add", "src")
    git(repo, "commit", "-q", "-m", "more")
    (repo / "src/crlf.txt").write_bytes(b"one\r\ntwo\r\nthree\r\n")
    (repo / "src/latin.txt").write_bytes("caf\xe9 au lait\n".encode("latin-1"))
    (repo / "src/new_crlf.txt").write_bytes(b"new\r\nfile\r\n")
    write(repo, "src/one.py", "one = 2\n")

    carry_back(repo, tmp_path)

    assert (repo / "src/crlf.txt").read_bytes() == b"one\r\ntwo\r\nthree\r\n"
    assert (repo / "src/latin.txt").read_bytes() == "caf\xe9 au lait\n".encode("latin-1")
    assert (repo / "src/new_crlf.txt").read_bytes() == b"new\r\nfile\r\n"
    assert (repo / "src/one.py").read_text() == "one = 2\n"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("diff.external", "true"),
        ("diff.noprefix", "true"),
        ("diff.mnemonicPrefix", "true"),
        ("color.diff", "always"),
        ("color.ui", "always"),
    ],
)
def test_the_patch_is_the_same_whatever_the_users_diff_config_says(
    repo: Path, tmp_path: Path, key: str, value: str
) -> None:
    write(repo, "src/one.py", "one = 2\n")
    write(repo, "src/fresh.py", "fresh = 1\n")
    plain = tree_patch(repo)
    git(repo, "config", key, value)

    configured = tree_patch(repo)

    assert configured == plain
    assert "--- a/src/one.py\n+++ b/src/one.py" in configured
    assert "+++ b/src/fresh.py" in configured
    carry_back(repo, tmp_path)
    assert (repo / "src/fresh.py").read_text() == "fresh = 1\n"


def test_the_patch_ignores_a_textconv_filter_the_users_attributes_name(repo: Path) -> None:
    (repo / ".gitattributes").write_text("*.py diff=shout\n")
    git(repo, "config", "diff.shout.textconv", "tr a-z A-Z <")
    write(repo, "src/one.py", "one = 2\n")

    assert "+one = 2" in tree_patch(repo)


# --- ITERATION_<request>.patch ------------------------------------------------------------


def test_the_iteration_patch_is_written_under_the_request_name(tmp_path: Path) -> None:
    path = files.write_iteration_patch(tmp_path, REQUEST, "diff text\n")

    assert path == tmp_path / f"ITERATION_{REQUEST}.patch"
    assert path.read_text() == "diff text\n"


def test_writing_the_iteration_patch_again_changes_nothing_and_leaves_no_temporary(
    tmp_path: Path,
) -> None:
    path = files.write_iteration_patch(tmp_path, REQUEST, "diff text\n")
    stamp = path.stat().st_mtime_ns

    files.write_iteration_patch(tmp_path, REQUEST, "diff text\n")

    assert path.stat().st_mtime_ns == stamp
    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_a_patch_already_written_stands_when_the_call_runs_again_with_an_empty_one(
    tmp_path: Path,
) -> None:
    files.write_iteration_patch(tmp_path, REQUEST, "the iteration's work\n")

    path = files.write_iteration_patch(tmp_path, REQUEST, "")

    assert path.read_text() == "the iteration's work\n"


def test_the_iteration_patch_refuses_a_name_that_is_not_a_request_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a request id"):
        files.write_iteration_patch(tmp_path, "../escape", "x")


# --- WORKER_<request>.json ----------------------------------------------------------------


def write_worker(task_dir: Path, result: object = RESULT_OBJECT) -> Path:
    return files.write_worker_end(
        task_dir,
        REQUEST,
        argv=["claude", "-p", "--max-turns", "30"],
        exit_code=0,
        max_turns=30,
        max_budget_usd=2.0,
        stdout_tail="{...}",
        result=result,  # type: ignore[arg-type]
    )


def test_a_worker_file_round_trips_into_an_ended_worker(tmp_path: Path) -> None:
    write_worker(tmp_path)

    assert files.read_worker_end(tmp_path, REQUEST) == WorkerEnd(
        session_id="6b1f0c2e",
        subtype="success",
        final_text="All done.",
        cost_usd=0.25,
        denials=2,
        num_turns=4,
        max_turns=30,
    )


def test_the_worker_file_is_the_document_the_design_names(tmp_path: Path) -> None:
    path = write_worker(tmp_path)

    document = json.loads(path.read_text())

    assert path.name == f"WORKER_{REQUEST}.json"
    assert document == {
        "v": 1,
        "argv": ["claude", "-p", "--max-turns", "30"],
        "exit": 0,
        "max_turns": 30,
        "max_budget_usd": 2.0,
        "stdout_tail": "{...}",
        "result": RESULT_OBJECT,
    }


def test_no_worker_file_reads_as_absent(tmp_path: Path) -> None:
    assert files.read_worker_end(tmp_path, REQUEST) is None


@pytest.mark.parametrize("result", [None, ["not", "an", "object"], "text", 3])
def test_a_worker_that_exited_without_a_result_object_reads_as_no_result(
    tmp_path: Path, result: object
) -> None:
    write_worker(tmp_path, result)

    read = files.read_worker_end(tmp_path, REQUEST)

    assert isinstance(read, NoWorkerResult)
    assert f"left no usable result; see WORKER_{REQUEST}.json" in read.detail


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '{"v": 2, "max_turns": 3, "result": {}}',
        '{"v": 1, "result": {"session_id": "s", "subtype": "success"}}',
        '{"v": 1, "max_turns": true, "result": {"session_id": "s", "subtype": "success"}}',
        '{"v": 1, "max_turns": 3, "result": {"subtype": "success"}}',
        '{"v": 1, "max_turns": 3, "result": {"session_id": "", "subtype": "success"}}',
        '{"v": 1, "max_turns": 3, "result": {"session_id": "s"}}',
    ],
)
def test_a_malformed_worker_file_is_never_an_ended_worker(tmp_path: Path, text: str) -> None:
    (tmp_path / f"WORKER_{REQUEST}.json").write_text(text)

    assert isinstance(files.read_worker_end(tmp_path, REQUEST), NoWorkerResult)


def test_a_result_object_without_the_optional_fields_reads_them_as_unknown(
    tmp_path: Path,
) -> None:
    write_worker(tmp_path, {"session_id": "s1", "subtype": "error_max_turns"})

    assert files.read_worker_end(tmp_path, REQUEST) == WorkerEnd(
        session_id="s1",
        subtype="error_max_turns",
        final_text=None,
        cost_usd=None,
        denials=0,
        num_turns=None,
        max_turns=30,
    )


@pytest.mark.parametrize("cost", ["0.5", True, -1, float("nan"), float("inf"), None])
def test_a_cost_that_is_not_a_non_negative_number_reads_as_unknown(
    tmp_path: Path, cost: object
) -> None:
    write_worker(tmp_path, {**RESULT_OBJECT, "total_cost_usd": cost})

    read = files.read_worker_end(tmp_path, REQUEST)

    assert isinstance(read, WorkerEnd)
    assert read.cost_usd is None


def test_an_integer_cost_reads_as_a_float(tmp_path: Path) -> None:
    write_worker(tmp_path, {**RESULT_OBJECT, "total_cost_usd": 2})

    read = files.read_worker_end(tmp_path, REQUEST)

    assert isinstance(read, WorkerEnd)
    assert read.cost_usd == 2.0
    assert isinstance(read.cost_usd, float)


def test_writing_the_same_worker_file_again_changes_nothing_and_leaves_no_temporary(
    tmp_path: Path,
) -> None:
    path = write_worker(tmp_path)
    stamp = path.stat().st_mtime_ns

    write_worker(tmp_path)

    assert path.stat().st_mtime_ns == stamp
    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_a_write_that_fails_part_way_leaves_the_old_worker_file_and_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_worker(tmp_path)
    before = path.read_bytes()

    def refuse(source: object, target: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        write_worker(tmp_path, {**RESULT_OBJECT, "result": "a different ending"})

    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_the_worker_writer_refuses_a_name_that_is_not_a_request_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a request id"):
        files.write_worker_end(
            tmp_path,
            "Bad Name",
            argv=[],
            exit_code=0,
            max_turns=1,
            max_budget_usd=1.0,
            stdout_tail="",
            result=None,
        )
