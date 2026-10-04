"""Committed renders are a pure function of the model source, and the gates keep them so.

Regenerating offline, twice in a row, reproduces the committed renders byte for
byte. When a model source change is staged, the pre-commit regeneration refreshes
and stages the renders, lets the commit proceed with a warning when the toolchain
is absent, and aborts with the failing step's message when regeneration fails. The
CI drift gate fails a change whose committed renders differ from a fresh
regeneration and passes one whose renders match.
"""

from __future__ import annotations

import shutil

import pytest

from tests.acceptance.drivers.diagram_regen import (
    MODEL_SOURCE,
    RENDER_DIR,
    changed_renders,
    git,
    rename_developer,
    require_pinned_toolchain,
    run_drift_gate,
    run_drift_gate_regeneration,
    run_precommit_regeneration,
    scratch_checkout,
    staged_paths,
    unstaged_render_changes,
)

NEW_NAME = "Developer Renamed For Regeneration"
MINIMAL_PATH = "/usr/bin:/bin"
FAILURE_MESSAGE = "simulated regeneration failure"


@pytest.fixture
def checkout(tmp_path):
    return scratch_checkout(tmp_path / "repo")


@pytest.fixture
def staged_model_change(checkout):
    rename_developer(checkout, NEW_NAME)
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
        NEW_NAME in (staged_model_change / p).read_text(encoding="utf-8") for p in staged_renders
    )
    assert unstaged_render_changes(staged_model_change) == []


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
