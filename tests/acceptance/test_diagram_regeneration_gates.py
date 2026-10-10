"""Committed renders are a pure function of the model source, and the gates keep them so.

Regenerating offline, twice in a row, reproduces the committed renders byte for
byte. When a model source change is staged, the pre-commit regeneration refreshes
and stages the renders, lets the commit proceed with a warning when the toolchain
is absent, and aborts with the failing step's message when regeneration fails. The
CI drift gate fails a change whose committed renders differ from a fresh
regeneration and passes one whose renders match. A real commit from a linked worktree,
where git exports `GIT_DIR` to its hooks, commits the refreshed renders beside the model
change and nothing else.
"""

from __future__ import annotations

import shutil

import pytest

from tests.acceptance.drivers.diagram_regen import (
    HOOK_VARIABLES,
    MODEL_SOURCE,
    RENDER_DIR,
    add_empty_view,
    changed_renders,
    commit_through_the_hook,
    committed_paths,
    empty_the_model,
    git,
    hook_saw,
    linked_worktree,
    rename_developer,
    require_pinned_toolchain,
    run_drift_gate,
    run_drift_gate_regeneration,
    run_precommit_regeneration,
    scratch_checkout,
    staged_paths,
    unstaged_render_changes,
)
from tests.acceptance.drivers.svg_render import read_render

NEW_NAME = "Developer Renamed For Regeneration"
MINIMAL_PATH = "/usr/bin:/bin"
FAILURE_MESSAGE = "simulated regeneration failure"
EMPTY_VIEW = "probe_empty_view"


@pytest.fixture
def checkout(tmp_path):
    return scratch_checkout(tmp_path / "repo")


@pytest.fixture
def staged_model_change(checkout):
    rename_developer(checkout, NEW_NAME)
    git(checkout, "add", MODEL_SOURCE.as_posix())
    return checkout


@pytest.fixture
def staged_model_change_in_a_linked_worktree(checkout):
    worktree = linked_worktree(checkout)
    rename_developer(worktree, NEW_NAME)
    git(worktree, "add", MODEL_SOURCE.as_posix())
    return worktree


@pytest.fixture
def staged_empty_view(checkout):
    add_empty_view(checkout, EMPTY_VIEW)
    git(checkout, "add", MODEL_SOURCE.as_posix())
    return checkout


@pytest.fixture
def staged_empty_model(checkout):
    empty_the_model(checkout)
    git(checkout, "add", MODEL_SOURCE.as_posix())
    return checkout


@pytest.fixture
def failing_toolchain(tmp_path):
    stubs = tmp_path / "failing-toolchain"
    stubs.mkdir()
    for name in ("likec4", "d2"):
        stub = stubs / name
        stub.write_text(f"#!/bin/sh\necho '{FAILURE_MESSAGE}' >&2\nexit 3\n", encoding="utf-8")
        stub.chmod(0o755)
    return stubs


def test_regenerating_twice_offline_reproduces_the_committed_renders_byte_for_byte(
    checkout,
) -> None:
    require_pinned_toolchain()

    first = run_drift_gate_regeneration(checkout)
    after_first = changed_renders(checkout)
    second = run_drift_gate_regeneration(checkout)
    after_second = changed_renders(checkout)

    assert (first.returncode, second.returncode) == (0, 0), (
        f"regeneration failed:\n{first.output}\n{second.output}"
    )
    assert (after_first, after_second) == ([], []), (
        "regenerated renders differ from the committed ones"
    )


def test_staging_a_model_change_regenerates_and_stages_the_renders(staged_model_change) -> None:
    require_pinned_toolchain()

    result = run_precommit_regeneration(staged_model_change)

    staged_renders = [
        p
        for p in staged_paths(staged_model_change)
        if p.startswith(RENDER_DIR.as_posix()) and p.endswith(".svg")
    ]
    assert result.returncode == 0, f"regeneration hook failed:\n{result.stdout}{result.stderr}"
    assert staged_renders, "no refreshed render was staged with the model change"
    assert any(
        read_render(staged_model_change / p).element_block(NEW_NAME) is not None
        for p in staged_renders
    ), "no staged render draws an element named after the changed model"
    assert unstaged_render_changes(staged_model_change) == []


def test_a_real_commit_from_a_linked_worktree_commits_the_renders_beside_the_model_and_nowhere_else(
    staged_model_change_in_a_linked_worktree,
) -> None:
    require_pinned_toolchain()
    worktree = staged_model_change_in_a_linked_worktree

    result = commit_through_the_hook(worktree, "rename the developer")

    assert result.returncode == 0, f"the commit failed:\n{result.stdout}{result.stderr}"
    assert hook_saw(worktree) == set(HOOK_VARIABLES), (
        f"git exported {sorted(hook_saw(worktree))} to the hook, not a hook's environment"
    )
    committed = committed_paths(worktree)
    renders = [p for p in committed if p.startswith(f"{RENDER_DIR.as_posix()}/")]
    assert renders, f"the commit holds no refreshed render: {committed}"
    beyond = sorted(set(committed) - {MODEL_SOURCE.as_posix(), *renders})
    assert not beyond, f"the commit holds paths beyond the model and its renders: {beyond}"
    assert any(
        read_render(worktree / p).element_block(NEW_NAME) is not None
        for p in renders
        if p.endswith(".svg")
    ), "no committed render draws the renamed element"
    assert git(worktree, "status", "--porcelain", "--untracked-files=all").stdout == "", (
        "the hook left changes outside the commit"
    )


def test_a_commit_proceeds_with_a_warning_when_the_toolchain_is_absent(staged_model_change) -> None:
    if shutil.which("likec4", path=MINIMAL_PATH) or shutil.which("d2", path=MINIMAL_PATH):
        pytest.skip(
            "the toolchain is installed in a system directory; its absence cannot be arranged"
        )

    result = run_precommit_regeneration(staged_model_change, path_override=MINIMAL_PATH)

    output = (result.stdout + result.stderr).casefold()
    assert result.returncode == 0, f"the commit was blocked without a toolchain:\n{output}"
    assert any(word in output for word in ("warn", "skip", "not installed")), (
        f"no warning was printed:\n{output}"
    )


def test_a_failing_regeneration_aborts_the_commit_with_the_failing_step_message(
    staged_model_change, failing_toolchain
) -> None:
    result = run_precommit_regeneration(staged_model_change, path_prefix=failing_toolchain)

    assert result.returncode != 0, "the commit was allowed although regeneration failed"
    assert FAILURE_MESSAGE in result.stdout + result.stderr


def test_the_drift_gate_fails_a_change_whose_committed_render_differs(checkout) -> None:
    require_pinned_toolchain()
    drifted = sorted((checkout / RENDER_DIR).glob("*.svg"))[0]
    drifted.write_text(drifted.read_text(encoding="utf-8") + "<!-- drift -->\n", encoding="utf-8")
    git(checkout, "commit", "-q", "--no-verify", "-am", "drift one render")

    result = run_drift_gate(checkout)

    assert result.returncode != 0, f"the drift gate passed a drifted render {drifted.name}"


def test_the_drift_gate_passes_a_change_whose_renders_match(checkout) -> None:
    require_pinned_toolchain()

    result = run_drift_gate(checkout)

    assert result.returncode == 0, (
        f"the drift gate failed matching renders at {result.failed_step}:\n{result.output[-2000:]}"
    )


def test_a_declared_view_that_draws_nothing_aborts_the_commit_naming_that_view(
    staged_empty_view,
) -> None:
    require_pinned_toolchain()

    result = run_precommit_regeneration(staged_empty_view)

    assert result.returncode != 0, (
        "the commit was allowed although a declared view rendered no element"
    )
    assert EMPTY_VIEW in result.stdout + result.stderr, (
        "the abort message does not name the failing view"
    )


def test_a_model_source_that_records_nothing_aborts_the_commit(staged_empty_model) -> None:
    require_pinned_toolchain()

    result = run_precommit_regeneration(staged_empty_model)

    assert result.returncode != 0, (
        "the commit was allowed although the model yields no view showing an element"
    )
    assert (result.stdout + result.stderr).strip(), (
        "the commit was aborted without a message naming the failure"
    )


def test_the_drift_gate_fails_a_change_that_adds_a_view_drawing_nothing(checkout) -> None:
    require_pinned_toolchain()
    add_empty_view(checkout, EMPTY_VIEW)
    git(checkout, "commit", "-q", "--no-verify", "-am", "declare an empty view")

    result = run_drift_gate(checkout)

    assert result.returncode != 0, "the drift gate passed a declared view that renders no element"


def test_the_drift_gate_fails_a_change_whose_model_records_nothing(checkout) -> None:
    require_pinned_toolchain()
    empty_the_model(checkout)
    git(checkout, "commit", "-q", "--no-verify", "-am", "empty the model")

    result = run_drift_gate(checkout)

    assert result.returncode != 0, (
        "the drift gate passed a model source that yields no view showing an element"
    )


def test_the_drift_gate_fails_when_a_toolchain_step_reports_an_error(
    checkout, failing_toolchain
) -> None:
    result = run_drift_gate(checkout, path_prefix=failing_toolchain)

    assert result.returncode != 0, "the drift gate passed although the toolchain reported an error"
