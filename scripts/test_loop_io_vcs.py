"""Tests for the git and command adapters of the step-loop driver (``scripts/_step_loop_io.py``).

The git half runs real ``git`` in temporary repositories built here: every case commits by
explicit path next to a staged decoy, an unstaged edit and an untracked file, and reads the
tree back afterwards. The runner half runs real child processes; the resolver is replaced by
a stub script except in the one test that pins the shape of its real answer.
"""

from __future__ import annotations

import json
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_io as step_io  # noqa: E402
from _git_runner import run_git  # noqa: E402
from _step_loop_io import (  # noqa: E402
    CommandRun,
    CommitInterrupted,
    CommitRefused,
    Committed,
    NothingToCommit,
    OutsideRepoError,
    ScopeRuns,
    ScopeUnresolved,
    TreeDisturbed,
    commit_paths,
    normalise_path,
    paths_differing_from_head,
    run_check,
    run_command,
    run_derived_scope,
    snapshot_outside,
    split_outer_loop,
)

REPO_ROOT = SCRIPT_DIR.parent
BASE_FILES = {
    "a.py": "a = 1\n",
    "b.py": "b = 1\n",
    "decoy.txt": "decoy\n",
    "notes.txt": "notes\n",
    "weird1.txt": "plain\n",
    "weird[1].txt": "literal\n",
    "tests/acceptance/test_outer.py": "outer = 1\n",
    "tests/test_inner.py": "inner = 1\n",
}
MESSAGE = "Add the thing\n\nA body line naming the driver.\n\nStep-Loop-Request: abc123\n"
SHORT_TIMEOUT = 0.5
OUTER = "tests/acceptance/test_outer.py"


def git(repo: Path, *args: str) -> str:
    done = run_git(repo, *args)
    assert done.returncode == 0, done.stderr
    return done.stdout


def write(repo: Path, rel: str, text: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def install_hook(repo: Path, body: str) -> None:
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\n" + body)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def committed_files(repo: Path) -> set[str]:
    return set(
        git(repo, "diff-tree", "--root", "-r", "--no-commit-id", "--name-only", "HEAD").split()
    )


def staged_names(repo: Path) -> str:
    return git(repo, "diff", "--cached", "--name-only")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    settings = {
        "user.name": "Tester",
        "user.email": "tester@example.invalid",
        "commit.gpgsign": "false",
        "core.hooksPath": str(root / ".git" / "hooks"),
    }
    for key, value in settings.items():
        git(root, "config", key, value)
    for rel, text in BASE_FILES.items():
        write(root, rel, text)
    git(root, "add", "--all")
    git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def surrounded(repo: Path) -> Path:
    """The repo with a unstaged edit and an untracked file outside the paths a test commits."""
    write(repo, "notes.txt", "notes, edited\n")
    write(repo, "scratch.txt", "untracked\n")
    write(repo, "a.py", "a = 2\n")
    return repo


# --- Outer-loop filter -------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "tests/acceptance/test_x.py",
        "tests/acceptance/drivers/d.py",
        "tests/e2e/test_y.py",
    ],
)
def test_outer_loop_directories_are_withheld_whatever_the_plan_says(path: str) -> None:
    assert split_outer_loop(["src/a.py", path]) == (("src/a.py",), (path,))


@pytest.mark.parametrize(
    "entry",
    [
        "docs/outer.md",
        "docs/outer.md::check_it",
        "docs/outer.md::check_it[case 1]",
        "docs/",
        "docs",
        "./docs/outer.md",
        "docs/../docs/outer.md::check_it",
    ],
)
def test_a_read_only_entry_withholds_its_path_in_every_form(entry: str) -> None:
    kept, withheld = split_outer_loop(["docs/outer.md", "src/a.py"], [entry])

    assert (kept, withheld) == (("src/a.py",), ("docs/outer.md",))


@pytest.mark.parametrize(
    ("spelling", "name"),
    [
        ("./tests/acceptance/x.py", "tests/acceptance/x.py"),
        ("scripts/../tests/e2e/x.py", "tests/e2e/x.py"),
        ("tests/acceptance", "tests/acceptance"),
        ("tests/e2e/", "tests/e2e"),
    ],
)
def test_outer_loop_files_are_found_under_every_spelling_of_their_path(
    spelling: str, name: str
) -> None:
    assert split_outer_loop([spelling, "src/a.py"]) == (("src/a.py",), (name,))


def test_a_bracketed_file_name_is_a_path_not_a_node_id() -> None:
    kept, withheld = split_outer_loop(["weird[1].txt", "weird1.txt"], ["weird[1].txt"])

    assert (kept, withheld) == (("weird1.txt",), ("weird[1].txt",))


@pytest.mark.parametrize("spelling", ["a.py", "./a.py", "x/../a.py", "./x/./../a.py"])
def test_every_spelling_of_a_path_normalises_to_one_name(spelling: str) -> None:
    assert normalise_path(spelling) == "a.py"


def test_a_directory_loses_its_trailing_slash() -> None:
    assert normalise_path("tests/acceptance/") == "tests/acceptance"


def test_an_absolute_path_is_made_relative_to_the_root(repo: Path) -> None:
    assert normalise_path(str(repo / "tests" / ".." / "a.py"), repo) == "a.py"


@pytest.mark.parametrize("escaping", ["../a.py", "x/../../a.py", "/etc/passwd"])
def test_a_path_that_leaves_the_repository_is_refused(escaping: str) -> None:
    with pytest.raises(OutsideRepoError, match="outside the repository"):
        normalise_path(escaping)


def test_a_read_only_entry_does_not_withhold_a_longer_name() -> None:
    paths = ["docs/outer.md.bak", "docs/outer.mdx", "tests/acceptance_helpers.py"]

    assert split_outer_loop(paths, ["docs/outer.md"]) == (tuple(paths), ())


def test_the_kept_paths_keep_their_order() -> None:
    kept, _ = split_outer_loop(["z.py", OUTER, "a.py", "m.py"])

    assert kept == ("z.py", "a.py", "m.py")


# --- Which declared paths differ from HEAD -----------------------------------------------


def test_modified_staged_untracked_and_deleted_paths_differ_from_head(repo: Path) -> None:
    write(repo, "a.py", "a = 2\n")
    write(repo, "b.py", "b = 2\n")
    git(repo, "add", "b.py")
    write(repo, "new.py", "new = 1\n")
    (repo / "decoy.txt").unlink()
    declared = ["new.py", "decoy.txt", "b.py", "a.py"]

    assert paths_differing_from_head(repo, declared) == ("a.py", "b.py", "decoy.txt", "new.py")


def test_unchanged_paths_are_left_out(repo: Path) -> None:
    write(repo, "b.py", "b = 2\n")

    assert paths_differing_from_head(repo, ["a.py", "b.py", "notes.txt"]) == ("b.py",)


@pytest.mark.parametrize("spelling", ["tests", "./tests/", "tests/../tests"])
def test_a_declared_directory_expands_to_the_changed_files_under_it(
    repo: Path, spelling: str
) -> None:
    write(repo, "tests/test_inner.py", "inner = 2\n")
    write(repo, "tests/new_test.py", "new = 1\n")
    write(repo, "a.py", "a = 2\n")

    assert paths_differing_from_head(repo, [spelling]) == (
        "tests/new_test.py",
        "tests/test_inner.py",
    )


@pytest.mark.parametrize("spelling", ["./a.py", "x/../a.py", "{root}/a.py"])
def test_a_differently_spelled_path_still_reads_as_changed(repo: Path, spelling: str) -> None:
    write(repo, "a.py", "a = 2\n")

    assert paths_differing_from_head(repo, [spelling.format(root=repo)]) == ("a.py",)


def test_no_declared_path_asks_git_nothing(repo: Path) -> None:
    write(repo, "a.py", "a = 2\n")

    assert paths_differing_from_head(repo, []) == ()


# --- The snapshot of the tree outside the paths ------------------------------------------


def test_the_snapshot_holds_what_lies_outside_the_paths(surrounded: Path) -> None:
    write(surrounded, "decoy.txt", "decoy, staged\n")
    git(surrounded, "add", "decoy.txt")

    snap = snapshot_outside(surrounded, frozenset({"a.py"}))

    assert (
        [p for p, _ in snap.staged],
        [p for p, _ in snap.unstaged],
        [p for p, _ in snap.untracked],
    ) == (["decoy.txt"], ["notes.txt"], ["scratch.txt"])


def test_the_snapshot_leaves_out_the_paths_themselves(surrounded: Path) -> None:
    snap = snapshot_outside(surrounded, frozenset({"a.py", "notes.txt", "scratch.txt"}))

    assert (snap.staged, snap.unstaged, snap.untracked, snap.unstaged_diff) == ((), (), (), "")


def test_two_snapshots_of_one_tree_are_equal_and_a_changed_file_is_named(
    surrounded: Path,
) -> None:
    pathspec = frozenset({"a.py"})
    first = snapshot_outside(surrounded, pathspec)
    same = snapshot_outside(surrounded, pathspec)
    write(surrounded, "notes.txt", "notes, edited again\n")
    write(surrounded, "later.txt", "appeared\n")
    later = snapshot_outside(surrounded, pathspec)

    assert (first == same, first.paths_differing(later)) == (True, ("later.txt", "notes.txt"))


def test_a_deleted_unstaged_file_is_marked_not_hashed(repo: Path) -> None:
    (repo / "b.py").unlink()

    snap = snapshot_outside(repo, frozenset())

    assert snap.unstaged == (("b.py", "deleted"),)


def test_the_patch_text_carries_the_unstaged_diff_and_the_untracked_blob(
    surrounded: Path,
) -> None:
    text = snapshot_outside(surrounded, frozenset({"a.py"})).patch_text()
    blob = git(surrounded, "hash-object", "scratch.txt").strip()

    assert ("+notes, edited" in text, f"scratch.txt  {blob}" in text) == (True, True)


# --- The commit by explicit path ---------------------------------------------------------


def test_a_commit_holds_exactly_the_paths(surrounded: Path) -> None:
    write(surrounded, "b.py", "b = 2\n")

    outcome = commit_paths(surrounded, ["a.py", "b.py"], MESSAGE)

    assert (outcome, committed_files(surrounded)) == (
        Committed(head(surrounded), ("a.py", "b.py"), ()),
        {"a.py", "b.py"},
    )


def test_the_message_reaches_the_commit_verbatim(surrounded: Path) -> None:
    commit_paths(surrounded, ["a.py"], MESSAGE)

    assert git(surrounded, "log", "-1", "--format=%B").strip() == MESSAGE.strip()


def test_an_unstaged_edit_and_an_untracked_file_survive_byte_identical(surrounded: Path) -> None:
    commit_paths(surrounded, ["a.py"], MESSAGE)

    assert (
        (surrounded / "notes.txt").read_bytes(),
        (surrounded / "scratch.txt").read_bytes(),
        git(surrounded, "status", "--porcelain").splitlines(),
    ) == (b"notes, edited\n", b"untracked\n", [" M notes.txt", "?? scratch.txt"])


def test_a_decoy_staged_before_the_call_is_refused_and_stays_staged(surrounded: Path) -> None:
    write(surrounded, "decoy.txt", "decoy, staged\n")
    git(surrounded, "add", "decoy.txt")
    before = head(surrounded)

    outcome = commit_paths(surrounded, ["a.py"], MESSAGE)

    assert (
        isinstance(outcome, TreeDisturbed),
        outcome.paths,
        outcome.sha,
        staged_names(surrounded),
        head(surrounded),
    ) == (True, ("decoy.txt",), None, "decoy.txt\n", before)


def test_a_refused_tree_is_not_repaired_the_declared_path_stays_unstaged(
    surrounded: Path,
) -> None:
    write(surrounded, "decoy.txt", "decoy, staged\n")
    git(surrounded, "add", "decoy.txt")

    commit_paths(surrounded, ["a.py"], MESSAGE)

    assert git(surrounded, "status", "--porcelain").splitlines() == [
        " M a.py",
        "M  decoy.txt",
        " M notes.txt",
        "?? scratch.txt",
    ]


def test_an_outer_loop_file_the_plan_declares_is_never_committed(surrounded: Path) -> None:
    write(surrounded, OUTER, "outer = 2\n")

    outcome = commit_paths(surrounded, ["a.py", OUTER], MESSAGE)

    assert (
        outcome.withheld,
        committed_files(surrounded),
        git(surrounded, "diff", "--name-only"),
    ) == (
        (OUTER,),
        {"a.py"},
        f"notes.txt\n{OUTER}\n",
    )


def test_a_read_only_entry_of_any_step_keeps_a_file_out_of_the_commit(surrounded: Path) -> None:
    write(surrounded, "b.py", "b = 2\n")

    outcome = commit_paths(surrounded, ["a.py", "b.py"], MESSAGE, read_only=["b.py::test_it"])

    assert (outcome.withheld, committed_files(surrounded)) == (("b.py",), {"a.py"})


def test_only_outer_loop_paths_commit_nothing(surrounded: Path) -> None:
    write(surrounded, OUTER, "outer = 2\n")
    before = head(surrounded)

    outcome = commit_paths(surrounded, [OUTER], MESSAGE)

    assert (outcome, head(surrounded)) == (NothingToCommit((OUTER,)), before)


@pytest.mark.parametrize("paths", [[], ["b.py"]])
def test_paths_that_do_not_differ_commit_nothing(repo: Path, paths: list[str]) -> None:
    before = head(repo)

    assert (commit_paths(repo, paths, MESSAGE), head(repo)) == (NothingToCommit(()), before)


def test_a_differently_spelled_path_commits_under_its_clean_name(surrounded: Path) -> None:
    outcome = commit_paths(surrounded, ["./x/../a.py"], MESSAGE)

    assert (outcome, committed_files(surrounded)) == (
        Committed(head(surrounded), ("a.py",), ()),
        {"a.py"},
    )


def test_a_declared_directory_never_sweeps_an_outer_loop_file_in(repo: Path) -> None:
    write(repo, OUTER, "outer = 2\n")
    write(repo, "tests/test_inner.py", "inner = 2\n")

    outcome = commit_paths(repo, ["tests"], MESSAGE)

    assert (outcome, committed_files(repo), git(repo, "diff", "--name-only")) == (
        Committed(head(repo), ("tests/test_inner.py",), (OUTER,)),
        {"tests/test_inner.py"},
        f"{OUTER}\n",
    )


def test_an_outer_loop_directory_declared_alone_commits_nothing(repo: Path) -> None:
    write(repo, OUTER, "outer = 2\n")
    write(repo, "tests/acceptance/new_driver.py", "new = 1\n")
    before = head(repo)

    outcome = commit_paths(repo, ["tests/acceptance"], MESSAGE)

    assert (outcome, head(repo)) == (
        NothingToCommit(("tests/acceptance/new_driver.py", OUTER)),
        before,
    )


@pytest.mark.parametrize(
    "entry", ["./tests/test_inner.py::test_it", "tests/test_inner.py", "tests", "tests/../tests/"]
)
def test_a_read_only_entry_in_any_spelling_keeps_a_declared_directory_file_out(
    repo: Path, entry: str
) -> None:
    write(repo, "tests/test_inner.py", "inner = 2\n")
    write(repo, "a.py", "a = 2\n")

    outcome = commit_paths(repo, ["tests", "a.py"], MESSAGE, read_only=[entry])

    assert (outcome.files, outcome.withheld) == (("a.py",), ("tests/test_inner.py",))


def test_a_moved_file_with_identical_content_commits_without_a_false_disturbance(
    repo: Path,
) -> None:
    (repo / "a.py").rename(repo / "moved.py")

    outcome = commit_paths(repo, ["a.py", "moved.py"], MESSAGE)

    assert outcome == Committed(head(repo), ("a.py", "moved.py"), ())


def test_a_lock_that_stops_the_staging_is_a_refusal_not_an_exception(surrounded: Path) -> None:
    (surrounded / ".git" / "index.lock").write_text("")
    before = head(surrounded)

    outcome = commit_paths(surrounded, ["a.py"], MESSAGE)

    assert (
        isinstance(outcome, CommitRefused),
        "index.lock" in outcome.detail,
        head(surrounded),
    ) == (
        True,
        True,
        before,
    )


def test_hooks_see_no_global_literal_pathspec_setting(surrounded: Path) -> None:
    seen = surrounded.parent / "seen.txt"
    install_hook(
        surrounded, f'echo "${{GIT_LITERAL_PATHSPECS:-unset}}" > {shlex.quote(str(seen))}\n'
    )

    commit_paths(surrounded, ["a.py"], MESSAGE)

    assert seen.read_text() == "unset\n"


def test_a_deleted_and_a_new_path_commit_as_a_deletion_and_an_addition(repo: Path) -> None:
    (repo / "b.py").unlink()
    write(repo, "c.py", "c = 1\n")

    outcome = commit_paths(repo, ["b.py", "c.py"], MESSAGE)

    assert (outcome.files, git(repo, "show", "--name-status", "--format=").splitlines()) == (
        ("b.py", "c.py"),
        ["D\tb.py", "A\tc.py"],
    )


def test_a_path_with_glob_characters_names_only_itself(repo: Path) -> None:
    write(repo, "weird[1].txt", "literal, edited\n")
    write(repo, "weird1.txt", "plain, edited\n")

    commit_paths(repo, ["weird[1].txt"], MESSAGE)

    assert (committed_files(repo), git(repo, "status", "--porcelain").strip()) == (
        {"weird[1].txt"},
        "M weird1.txt",
    )


# --- Hooks that rewrite files ------------------------------------------------------------

REFORMAT_THEN_FAIL = """\
if grep -q ' $' a.py; then
  sed -i.bak 's/ *$//' a.py
  rm a.py.bak
  echo "reformatted a.py" >&2
  exit 1
fi
"""


def test_hooks_that_rewrote_a_file_get_one_restage_and_the_commit_lands(surrounded: Path) -> None:
    write(surrounded, "a.py", "a = 2 \n")
    install_hook(surrounded, REFORMAT_THEN_FAIL)

    outcome = commit_paths(surrounded, ["a.py"], MESSAGE)

    assert (
        isinstance(outcome, Committed),
        git(surrounded, "show", "HEAD:a.py"),
        (surrounded / "a.py").read_text(),
    ) == (True, "a = 2\n", "a = 2\n")


def test_hooks_that_keep_refusing_leave_a_refusal_with_their_words_and_no_commit(
    surrounded: Path,
) -> None:
    install_hook(surrounded, "echo 'lint says no' >&2\nexit 1\n")
    before = head(surrounded)

    outcome = commit_paths(surrounded, ["a.py"], MESSAGE)

    assert (
        isinstance(outcome, CommitRefused),
        "lint says no" in outcome.detail,
        head(surrounded),
    ) == (
        True,
        True,
        before,
    )


def test_a_refusal_that_moved_no_file_is_not_retried(surrounded: Path) -> None:
    counter = surrounded / "runs.log"
    install_hook(surrounded, f"echo run >> {shlex.quote(str(counter))}\nexit 1\n")

    commit_paths(surrounded, ["a.py"], MESSAGE)

    assert counter.read_text().splitlines() == ["run"]


@pytest.mark.parametrize(
    ("hook", "moved"),
    [
        ("echo stray > stray.txt\n", ("stray.txt",)),
        ("echo more >> notes.txt\n", ("notes.txt",)),
    ],
)
def test_a_hook_that_changes_the_tree_outside_the_paths_is_reported_as_a_disturbed_tree(
    surrounded: Path, hook: str, moved: tuple[str, ...]
) -> None:
    install_hook(surrounded, hook)

    outcome = commit_paths(surrounded, ["a.py"], MESSAGE)

    assert (isinstance(outcome, TreeDisturbed), outcome.paths, outcome.sha) == (
        True,
        moved,
        head(surrounded),
    )


def test_a_hook_that_adds_a_file_to_the_commit_breaks_the_file_set_check(surrounded: Path) -> None:
    install_hook(surrounded, "echo stray > stray.txt\ngit add stray.txt\n")

    outcome = commit_paths(surrounded, ["a.py"], MESSAGE)

    assert (isinstance(outcome, TreeDisturbed), outcome.paths, outcome.sha) == (
        True,
        ("stray.txt",),
        head(surrounded),
    )


def test_a_commit_that_outlives_its_bound_is_reported_with_the_lock_and_the_staged_files(
    surrounded: Path,
) -> None:
    install_hook(surrounded, "sleep 3\n")
    before = head(surrounded)

    outcome = commit_paths(surrounded, ["a.py"], MESSAGE, commit_timeout=0.5)

    assert (
        isinstance(outcome, CommitInterrupted),
        "exceeded" in outcome.detail,
        outcome.index_locked,
        outcome.after == snapshot_outside(surrounded, frozenset({"a.py"})),
        staged_names(surrounded),
        head(surrounded),
    ) == (True, True, True, True, "a.py\n", before)


def test_a_disturbance_hands_back_both_snapshots_for_the_caller_to_save(surrounded: Path) -> None:
    install_hook(surrounded, "echo more >> notes.txt\n")

    outcome = commit_paths(surrounded, ["a.py"], MESSAGE)

    assert (
        "+notes, edited" in outcome.before.patch_text(),
        "+more" in outcome.after.patch_text(),
    ) == (
        True,
        True,
    )


# --- The runner --------------------------------------------------------------------------


def py(code: str) -> tuple[str, ...]:
    return (sys.executable, "-c", code)


def test_a_command_run_holds_both_streams_and_the_return_code(tmp_path: Path) -> None:
    code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"

    run = run_command(py(code), tmp_path, 30)

    assert (run.output, run.returncode, run.problem, run.cwd) == (
        "out\nerr\n",
        3,
        None,
        str(tmp_path),
    )


def test_a_runner_is_never_asked_for_colour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    code = "import os; print(*(os.environ.get(k, '-') for k in ('FORCE_COLOR','CLICOLOR_FORCE','NO_COLOR','PY_COLORS')))"

    assert run_command(py(code), tmp_path, 30).output == "- - 1 0\n"


def test_a_command_that_outlives_its_timeout_reports_why_and_keeps_what_it_printed(
    tmp_path: Path,
) -> None:
    code = "import sys, time; print('started', flush=True); time.sleep(30)"

    run = run_command(py(code), tmp_path, SHORT_TIMEOUT)

    assert (run.returncode, run.problem, run.output) == (None, "timed out after 0.5s", "started\n")


def process_is_gone(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
        )
        if state.stdout.strip() == "" or state.stdout.strip().startswith("Z"):
            return True
        time.sleep(0.05)
    return False


def test_a_timeout_kills_the_commands_whole_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    code = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "print('ready', flush=True)\n"
        "time.sleep(60)\n"
    )

    run = run_command(py(code), tmp_path, 1.5)

    assert (run.problem, run.output, process_is_gone(int(pid_file.read_text()))) == (
        "timed out after 1.5s",
        "ready\n",
        True,
    )


def test_a_command_that_cannot_start_reports_why(tmp_path: Path) -> None:
    run = run_command(("no-such-program-here",), tmp_path, 30)

    assert (run.returncode, run.output, (run.problem or "").startswith("could not start")) == (
        None,
        "",
        True,
    )


@pytest.mark.parametrize(("returncode", "problem"), [(0, "both"), (None, None)])
def test_a_run_has_a_return_code_or_a_problem_never_both_or_neither(
    returncode: int | None, problem: str | None
) -> None:
    with pytest.raises(ValueError, match="never both"):
        CommandRun(("x",), ".", "", returncode, problem)


def test_the_check_command_is_split_like_a_shell_and_run_without_one(tmp_path: Path) -> None:
    command = f"{shlex.quote(sys.executable)} -c \"print('a b' + '$HOME')\""

    assert run_check(tmp_path, command).output == "a b$HOME\n"


def write_stub_resolver(tmp_path: Path, answer: str, exit_code: int = 0) -> Path:
    stub = tmp_path / "stub_resolver.py"
    stub.write_text(
        "import pathlib, sys\n"
        f"pathlib.Path({str(tmp_path / 'asked.txt')!r}).write_text(' '.join(sys.argv[1:]))\n"
        f"print({answer!r})\n"
        f"sys.exit({exit_code})\n"
    )
    return stub


def scope_answer(*invocations: dict) -> str:
    return json.dumps(
        {"schema": 2, "decision": "narrow", "pockets": [{"invocations": list(invocations)}]}
    )


def test_every_invocation_the_resolver_lists_runs_on_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pocket").mkdir()
    first = {"cwd": ".", "argv": list(py("print('one')"))}
    second = {"cwd": "pocket", "argv": list(py("import os; print(os.path.basename(os.getcwd()))"))}
    monkeypatch.setattr(
        step_io, "RESOLVER", write_stub_resolver(tmp_path, scope_answer(first, second))
    )

    result = run_derived_scope(tmp_path, ["a.py"])

    assert (
        isinstance(result, ScopeRuns),
        result.decision,
        [run.output for run in result.runs],
    ) == (True, "narrow", ["one\n", "pocket\n"])


def test_the_resolver_is_asked_for_json_about_the_changed_paths_in_this_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(step_io, "RESOLVER", write_stub_resolver(tmp_path, scope_answer()))

    run_derived_scope(tmp_path, ["a.py", "b.py"])

    asked = (tmp_path / "asked.txt").read_text()
    assert asked == f"--repo-root {tmp_path} --changed a.py b.py --json"


@pytest.mark.parametrize(
    ("answer", "exit_code"),
    [("usage: it broke", 2), ("not json at all", 0), ('{"schema": 2}', 0), ("[1, 2]", 0)],
)
def test_a_resolver_that_gives_no_plan_is_unresolved_never_an_empty_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str, exit_code: int
) -> None:
    monkeypatch.setattr(step_io, "RESOLVER", write_stub_resolver(tmp_path, answer, exit_code))

    result = run_derived_scope(tmp_path, ["a.py"])

    assert (isinstance(result, ScopeUnresolved), result.resolver.returncode) == (True, exit_code)


def test_the_real_resolver_answers_in_the_shape_the_runner_reads() -> None:
    resolver = run_command(
        (sys.executable, str(step_io.RESOLVER), "--repo-root", str(REPO_ROOT)) + (
            "--changed", "scripts/_step_loop_gate.py", "--json",
        ),
        REPO_ROOT,
        120,
    )  # fmt: skip

    plan = step_io._read_plan(resolver)

    assert plan is not None
    shapes = {frozenset(i) for pocket in plan["pockets"] for i in pocket["invocations"]}
    assert shapes == {frozenset({"cwd", "argv"})}
