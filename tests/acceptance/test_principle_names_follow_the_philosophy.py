"""The principle names every kernel's pointer carries follow the philosophy's principle headings.

A heading added to, removed from or renamed in the template's Principles section reaches the
pointer's list of names and its count once the kernels are regenerated, with no hand edit to
any source, and the freshness check refuses committed kernels that lag the template.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers import principle_names as names
from tests.acceptance.drivers.kernel_sandbox import Sandbox, regenerate

PROBE = "Probe Principle Of Record"
RENAMED = "Structural Grace"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def test_an_added_principle_heading_reaches_every_pointer_in_place_with_the_new_count(
    sandbox: Sandbox,
) -> None:
    names.add_principle(sandbox, PROBE, before="Root Causes Over Workarounds")
    regenerate(sandbox.root)

    assert names.disagreements(sandbox.root) == {}


def test_a_removed_principle_heading_leaves_every_pointer_with_the_smaller_count(
    sandbox: Sandbox,
) -> None:
    names.remove_principle(sandbox, names.EXEMPLAR)
    regenerate(sandbox.root)

    assert names.disagreements(sandbox.root) == {}
    assert [p for p in names.pointers(sandbox.root).values() if names.EXEMPLAR in p] == [], (
        "a pointer still names the removed principle"
    )


def test_a_renamed_principle_heading_is_named_by_its_new_name_in_every_pointer(
    sandbox: Sandbox,
) -> None:
    names.rename_principle(sandbox, names.EXEMPLAR, RENAMED)
    regenerate(sandbox.root)

    assert names.disagreements(sandbox.root) == {}
    assert [p for p in names.pointers(sandbox.root).values() if names.EXEMPLAR in p] == [], (
        "a pointer still names the principle by its old name"
    )


def test_the_freshness_check_fails_while_the_committed_kernels_lag_an_added_principle(
    sandbox: Sandbox,
) -> None:
    names.add_principle(sandbox, PROBE, before="Root Causes Over Workarounds")

    result = names.freshness_check(sandbox.root)

    assert result.exit_code != 0, f"stale kernels passed the freshness check:\n{result.output}"
