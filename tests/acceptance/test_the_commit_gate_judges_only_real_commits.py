"""The commit gate starts its checkers for every real commit and for no read-only command.

A Bash call that is not a commit -- the words git and commit only in its description or
transcript path, or as an argument of another git subcommand -- passes without any gated
checker starting. Every form that does record a commit, and any form the gate cannot read
with certainty, still starts them.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.drivers.bash_hooks import bash_payload, run_commit_gate, scratch_repo

READ_ONLY = {
    "description-says-commit": ("ls", {"description": "Check what git commit would record"}),
    "transcript-path-says-commit": (
        "ls",
        {"transcript_path": "/tmp/git-commit-review/transcript.jsonl"},
    ),
    "log-grep-for-commit": ("git log --grep=commit --oneline", {}),
    "show-described-as-commit": ("git show HEAD", {"description": "Show the last git commit"}),
}

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


@pytest.mark.parametrize("case", list(READ_ONLY))
def test_a_read_only_command_mentioning_a_commit_starts_no_checker(tmp_path, case):
    root = scratch_repo(tmp_path)
    command, fields = READ_ONLY[case]

    run = run_commit_gate(tmp_path, bash_payload(root, command, **fields))

    assert run.exit_code == 0, run
    assert run.checker_starts == 0, run


@pytest.mark.parametrize("case", list(REAL_COMMITS))
def test_every_real_commit_form_starts_the_checkers(tmp_path, case):
    root = scratch_repo(tmp_path)

    run = run_commit_gate(tmp_path, bash_payload(root, REAL_COMMITS[case]))

    assert run.checker_starts == 1, (json.dumps(REAL_COMMITS[case]), run)
