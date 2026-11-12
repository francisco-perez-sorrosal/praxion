"""A resolver run over a clean working tree says why it selected nothing.

With no change-set argument the resolver reads the working-tree diff and the untracked
files. On a clean tree it adds a line on stderr saying it read a clean tree, so it
selected nothing, and that `--changed-from` with a base revision judges committed
work; stdout and the exit status 0 are unchanged, and a run that reads any changed
path prints no such line.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.acceptance.drivers.refusal_messages import (
    WIDGET_PROJECT,
    resolve_working_tree,
    scratch_repo,
)

MODES = [pytest.param(False, id="plain"), pytest.param(True, id="json")]

# What the resolver printed on stdout for this clean repository before the change.
CLEAN_TREE_JSON = {
    "schema": 2,
    "changed": {"source": "working-tree", "paths": []},
    "decision": "nothing-to-run",
    "widen": [],
    "ignored_non_source": [],
    "pockets": [
        {
            "root": ".",
            "ecosystem": "python",
            "adapter": "python-derived",
            "selection": "nothing",
            "tests": [],
            "invocations": [],
        }
    ],
}


@pytest.mark.parametrize("as_json", MODES)
def test_a_clean_tree_run_says_on_stderr_that_it_read_a_clean_tree_and_names_changed_from(
    tmp_path: Path, as_json: bool
) -> None:
    repo = scratch_repo(tmp_path / "repo", WIDGET_PROJECT)

    run = resolve_working_tree(repo, as_json=as_json)

    assert run.exit_code == 0
    assert re.search(r"\bclean\b", run.stderr, re.IGNORECASE), run.stderr
    assert "--changed-from" in run.stderr, run.stderr


def test_a_clean_tree_run_prints_the_same_stdout_as_before(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path / "repo", WIDGET_PROJECT)

    plain = resolve_working_tree(repo, as_json=False)
    as_json = resolve_working_tree(repo, as_json=True)

    assert (plain.exit_code, plain.stdout) == (0, "")
    assert as_json.exit_code == 0
    assert json.loads(as_json.stdout) == CLEAN_TREE_JSON


@pytest.mark.parametrize(
    ("rel", "text"),
    [
        pytest.param("src/widget.py", "def value():\n    return 2\n", id="a-tracked-edit"),
        pytest.param("src/extra.py", "def extra():\n    return 3\n", id="an-untracked-file"),
    ],
)
@pytest.mark.parametrize("as_json", MODES)
def test_a_run_that_reads_a_changed_path_prints_no_clean_tree_line(
    tmp_path: Path, rel: str, text: str, as_json: bool
) -> None:
    repo = scratch_repo(tmp_path / "repo", WIDGET_PROJECT)
    (repo / rel).write_text(text, encoding="utf-8")

    run = resolve_working_tree(repo, as_json=as_json)

    assert run.exit_code == 0
    assert "--changed-from" not in run.stderr, run.stderr
