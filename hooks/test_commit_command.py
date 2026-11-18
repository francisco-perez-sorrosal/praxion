"""Tests for hooks/_commit_command.py, the commit gate's reader of whether a command commits.

The reader answers one of three words, and only `not-a-commit` lets the gate skip its
checkers, so each table below is a promise in one direction: every real commit and every
form the reader cannot read with certainty keeps the checkers running, and every read-only
form the gate exists to let through does let it through.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _commit_command as reader  # noqa: E402

READER = Path(reader.__file__).resolve()
GATE = READER.parent / "commit_gate.sh"

CHECKER_MARKER = "THE CHECKER RAN"

# The one `case` arm of the gate that lists the subcommands it decides in shell.
_SHELL_LIST_ARM = re.compile(r"^\s*((?:[a-z-]+ \| )+[a-z-]+)\) return 0 ;;$", re.MULTILINE)


def _shell_decided_subcommands() -> list[frozenset[str]]:
    """Every subcommand list the gate's shell stage decides by, read from its source."""
    arms = _SHELL_LIST_ARM.findall(GATE.read_text(encoding="utf-8"))
    return [frozenset(arm.split(" | ")) for arm in arms]


REAL_COMMITS = {
    "escaped-double-quotes": 'git commit -m "say \\"hi\\" to the widget"',
    "single-quotes": "git commit -m 'add widget'",
    "newline-in-message": "git commit -m 'first line\n\nbody line'",
    "add-and-commit": "git add widget.py && git commit -m 'add widget'",
    "add-or-commit": "git add widget.py || git commit -m 'add widget'",
    "add-semicolon-commit": "git add widget.py; git commit -m 'add widget'",
    "add-newline-commit": "git add widget.py\ngit commit -m 'add widget'",
    "directory-option": "git -C . commit -m 'add widget'",
    "environment-assignment": "GIT_AUTHOR_NAME=someone git commit -m 'add widget'",
    "amend": "git commit --amend --no-edit",
    "bash-c": "bash -c \"git commit -m 'add widget'\"",
    "sh-c": "sh -c 'git commit -m add-widget'",
}

READ_ONLY = {
    "no-git-at-all": "ls",
    "log-grep-for-commit": "git log --grep=commit --oneline",
    "show-head": "git show HEAD",
    "status": "git status",
    "log-grep-for-a-dashed-commit": "git log --grep=git-commit",
}

# One row per rule of the reader's table, in the table's order: the input and its verdict.
RULES = {
    "unbalanced-quote": ("git commit -m 'half", "uncertain"),
    "dangling-escape": ("git commit -m x \\", "uncertain"),
    "command-substitution": ('git commit -m "$(cat msg)"', "uncertain"),
    "backtick-substitution": ("git log --grep=`echo commit`", "uncertain"),
    "process-substitution-in": ("diff <(git log) <(git show commit)", "uncertain"),
    "process-substitution-out": ("git log --grep=commit > >(tee log)", "uncertain"),
    "eval": ("eval git commit -m x", "uncertain"),
    "eval-after-assignment": ("A=1 eval 'git commit -m x'", "uncertain"),
    "bash-c-read-only": ("bash -c 'git log --grep=commit'", "not-a-commit"),
    "login-shell-cluster": ("bash -lc 'git commit -m x'", "commit"),
    "shell-option-value": ("bash -o pipefail -c 'git commit -m x'", "commit"),
    "shell-by-path": ("/bin/zsh -c 'git commit -m x'", "commit"),
    "shell-behind-wrapper": ("sudo -u builder sh -c 'git commit -m x'", "commit"),
    "shell-c-without-script": ("bash -c", "uncertain"),
    "two-nested-shells": ("bash -c \"sh -c 'git commit -m x'\"", "commit"),
    "three-nested-shells": ('bash -c "sh -c \\"dash -c \'git log\'\\""', "uncertain"),
    "git-by-path": ("/usr/bin/git commit -m x", "commit"),
    "git-behind-env": ("env GIT_DIR=.git git commit -m x", "commit"),
    "git-behind-timeout": ("timeout 30 git commit -m x", "commit"),
    "git-config-option": ("git -c user.name=x commit -m y", "commit"),
    "config-value-without-a-commit": ("git -c user.name=x log", "not-a-commit"),
    "config-value-naming-a-commit": ("git -c alias.ci=commit log", "uncertain"),
    "config-env-value-naming-a-commit": (
        "git --config-env=alias.ci=commit_alias log",
        "uncertain",
    ),
    "git-dir-separate-value": ("git --git-dir .git commit -m y", "commit"),
    "git-dir-equals-value": ("git --git-dir=.git commit -m y", "commit"),
    "value-less-flags": ("git --no-pager -P --no-optional-locks commit -m y", "commit"),
    "missing-option-value": ("git -C", "uncertain"),
    "bare-git": ("git", "uncertain"),
    "assignment-ending-in-git": ("GIT_EXEC=/opt/git log --grep=commit", "uncertain"),
    "built-in-merge-no-commit": ("git merge --no-commit topic", "not-a-commit"),
    "built-in-help": ("git help commit", "not-a-commit"),
    "built-in-running-a-command-naming-a-commit": ("git rebase -x ./commit.sh main", "uncertain"),
    "option-running-a-command-naming-a-commit": (
        "git fetch --upload-pack=./commit.sh .",
        "uncertain",
    ),
    "branch-named-for-a-commit": ("git push origin commit-fix", "not-a-commit"),
    "alias": ("git ci -m commit", "uncertain"),
    "unknown-global-option": ("git --frobnicate commit -m x", "uncertain"),
    "dollar-in-subcommand": ("git $SUB -m commit", "uncertain"),
    "commit-tree-records-a-commit": ("git commit-tree HEAD^{tree} -m commit", "uncertain"),
    "commit-wins-over-uncertain": ("git ci x; git commit -m y", "commit"),
    "uncertain-wins-over-read-only": ("git log --grep=commit; git ci", "uncertain"),
    "every-git-word-is-read": ("git log --grep=x git commit -m y", "commit"),
    "unquoted-echo": ("echo git commit", "commit"),
    "redirection-target-skipped": ("git >/dev/null commit -m x", "commit"),
    "stderr-duplication": ("git commit -m x 2>&1 | tail -n 3", "commit"),
    "subshell": ("(cd widget && git commit -m x)", "commit"),
    "comment-sign-is-a-word": ("git log # then git commit -m x", "commit"),
}

# Forms that commit by a route the reader cannot follow: each must keep the checkers running.
OTHER_ROUTES = {
    "commit-as-a-wrapper-argument": "make commit",
    "commit-fed-to-xargs": "echo commit | xargs git",
    "git-in-a-variable": '"$GIT" commit -m x',
    "script-for-another-interpreter": "python -c \"import os; os.system('git commit -m x')\"",
    "script-for-a-git-built-in": "git rebase -x 'git commit --amend --no-edit' main",
    "commit-named-script-for-a-git-built-in": "git rebase -x ./scripts/commit.sh main",
    "commit-named-script-for-git-bisect": "git bisect run ./check-commit.sh",
    "commit-run-in-each-repository": "git for-each-repo --config=maintenance.repo commit -m x",
    "commit-named-tool-for-git-difftool": "git difftool -x ./commit.sh HEAD~1",
    "commit-run-in-each-repository-of-a-directory": "git -C repo for-each-repo --config=k commit -m x",
    "commit-named-tool-for-a-quoted-difftool": 'git "difftool" -x ./commit.sh HEAD~1',
    "commit-alias-run-in-each-repository": (
        "git -c alias.ci=commit for-each-repo --config=maintenance.repo ci --allow-empty -m x"
    ),
    "commit-named-tool-configured-for-difftool": "git -c difftool.t.cmd=./commit.sh difftool -y -t t",
    "commit-named-upload-pack-for-ls-remote": "git ls-remote --upload-pack=./commit.sh .",
    "commit-named-upload-pack-for-fetch": "git fetch --upload-pack ./commit.sh .",
    "commit-named-receive-pack-for-push": "git push --receive-pack=./commit.sh .",
    "commit-named-upload-pack-for-clone": "git clone -u ./commit.sh . copy",
    "commit-named-exec-for-archive": "git archive --remote=. --exec=./commit.sh HEAD",
    "commit-hook-run-by-git-hook": "git hook run post-commit",
    "commit-named-script-for-git-submodule": "git submodule foreach ./commit.sh",
    "commit-named-filter-for-git-filter-branch": "git filter-branch --tree-filter ./commit.sh HEAD",
    "dashed-git-commit": "git-commit -m x",
    "dashed-git-commit-by-path": "/usr/lib/git-core/git-commit -m x",
    "script-named-for-a-commit": "bash scripts/git-commit.sh",
    "script-named-for-a-commit-run-by-path": "./scripts/commit.sh",
    "script-named-for-a-commit-run-by-a-shell": "sh tools/do-commit",
    "file-named-for-a-commit": "cat commit-notes.md",
}

# Every command of the tables above that begins `git <a subcommand the gate decides in
# shell>`, so the shell stage may answer it before the reader is asked.
_TABLES = {
    **REAL_COMMITS,
    **READ_ONLY,
    **{case: command for case, (command, _) in RULES.items()},
    **OTHER_ROUTES,
}
_SHELL_PREFIX = re.compile(
    r"git (?:{})(?: |$)".format("|".join(frozenset().union(*_shell_decided_subcommands())))
)
SHELL_PREFIXED_ROWS = {
    case: command for case, command in _TABLES.items() if _SHELL_PREFIX.match(command)
}


@pytest.mark.parametrize("case", list(REAL_COMMITS))
def test_every_real_commit_form_reads_commit(case):
    assert reader.classify(REAL_COMMITS[case]) == "commit"


@pytest.mark.parametrize("case", list(READ_ONLY))
def test_a_read_only_form_reads_not_a_commit(case):
    assert reader.classify(READ_ONLY[case]) == "not-a-commit"


@pytest.mark.parametrize("case", list(RULES))
def test_each_rule_of_the_table_decides_its_form(case):
    command, verdict = RULES[case]

    assert reader.classify(command) == verdict, command


@pytest.mark.parametrize("case", list(OTHER_ROUTES))
def test_a_commit_by_another_route_is_never_read_as_none(case):
    assert reader.classify(OTHER_ROUTES[case]) == "uncertain"


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[1, 2]",
        json.dumps({"tool_name": "Bash"}),
        json.dumps({"tool_input": "git commit"}),
        json.dumps({"tool_input": {"command": ["git", "commit"]}}),
    ],
    ids=["not-json", "not-an-object", "no-tool-input", "tool-input-not-an-object", "not-a-string"],
)
def test_an_unreadable_payload_reads_uncertain(payload):
    assert reader.verdict_of(payload.encode()) == "uncertain"


def test_the_payload_is_decoded_once_so_an_escaped_word_is_read_as_written():
    payload = '{"tool_input": {"command": "git co\\u006dmit -m x"}}'

    assert reader.verdict_of(payload.encode()) == "commit"


@pytest.mark.parametrize(
    ("command", "verdict"),
    [("git log --grep=commit", "not-a-commit"), ("git commit -m x", "commit")],
    ids=["read-only", "commit"],
)
def test_the_reader_prints_one_word_as_the_gate_runs_it(command, verdict):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})

    run = subprocess.run(
        [sys.executable, "-I", "-S", str(READER)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert (run.returncode, run.stdout, run.stderr) == (0, verdict + "\n", "")


# ---------------------------------------------------------------------------
# The gate's shell stage answers only what the reader would answer the same way
# ---------------------------------------------------------------------------


def _checker_starts(command: str, tmp_path: Path) -> bool:
    """Whether the real gate, with the real reader beside it, starts its checker."""
    checker = tmp_path / "checker.py"
    checker.write_text(f"import sys\nsys.stdin.read()\nprint({CHECKER_MARKER!r})\n", "utf-8")
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    run = subprocess.run(
        [str(GATE), "--blocking", str(checker)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    return CHECKER_MARKER in run.stdout


def test_the_subcommands_the_gate_decides_in_shell_are_built_ins_the_reader_knows():
    shell_lists = _shell_decided_subcommands()

    assert len(shell_lists) == 1, f"expected one subcommand list in {GATE.name}"
    assert shell_lists[0], "the gate's subcommand list is empty"
    assert shell_lists[0] <= reader.GIT_BUILTINS, shell_lists[0] - reader.GIT_BUILTINS


@pytest.mark.parametrize("case", list(SHELL_PREFIXED_ROWS))
def test_a_row_the_shell_may_decide_gets_the_readers_answer_through_the_gate(case, tmp_path):
    command = SHELL_PREFIXED_ROWS[case]

    started = _checker_starts(command, tmp_path)

    assert started == (reader.classify(command) != "not-a-commit"), command


@pytest.mark.parametrize("case", list(REAL_COMMITS))
def test_every_real_commit_form_starts_the_checker_through_the_gate(case, tmp_path):
    assert _checker_starts(REAL_COMMITS[case], tmp_path), REAL_COMMITS[case]


# The gate's first text test lets a payload with no `git` in it pass, so only these of the
# other routes ever reach the reader.
ROUTES_NAMING_GIT = {case: command for case, command in OTHER_ROUTES.items() if "git" in command}


@pytest.mark.parametrize("case", list(ROUTES_NAMING_GIT))
def test_a_commit_by_another_route_starts_the_checker_through_the_gate(case, tmp_path):
    assert _checker_starts(ROUTES_NAMING_GIT[case], tmp_path), ROUTES_NAMING_GIT[case]
