"""A maintainer edits a process rule or reclassifies one of its sections, runs the regeneration
step, and commits: the kernel checks pass, a split recipient receives the edited rule as its
split text, and the main session and a whole recipient receive it whole.

The journey crosses the rule file, the commit-time kernel checks and the spawn and session
hooks, all on a sandbox copy of the plugin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_split as split
from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers.audience_split import INTERMEDIATE, PROTOCOL
from tests.acceptance.drivers.kernel_sandbox import Sandbox

EDITS = {
    "kept-span-edited-in-the-protocol": PROTOCOL,
    "kept-span-edited-in-the-intermediate-documents-rule": INTERMEDIATE,
    "dropped-span-edited-in-the-protocol": PROTOCOL,
    "dropped-section-reclassified-as-kept": PROTOCOL,
}


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture(params=sorted(EDITS))
def edited(
    request: pytest.FixtureRequest, template: Path, tmp_path: Path
) -> tuple[Sandbox, split.Unit]:
    sandbox = kernel_sandbox.new_sandbox(template, tmp_path / "plugin")
    split.plant(sandbox, request.param)
    split.bring_up_to_date(sandbox.root)
    return sandbox, EDITS[request.param]


def test_the_kernel_checks_pass_after_the_regeneration(edited: tuple[Sandbox, split.Unit]) -> None:
    sandbox, _ = edited

    verdict = split.kernel_gate(sandbox.root)

    assert not verdict.refused, verdict.output


def test_a_split_recipient_receives_the_edited_rule_as_its_split_text(
    edited: tuple[Sandbox, split.Unit], tmp_path: Path
) -> None:
    sandbox, unit = edited
    project = split.fresh_project(tmp_path / "project")

    received = split.spawn(sandbox.root, project, "praxion:verifier").text_of(unit)

    assert received == split.split_text(sandbox.root, unit)


def test_the_main_session_receives_the_edited_rule_whole(
    edited: tuple[Sandbox, split.Unit], tmp_path: Path
) -> None:
    sandbox, unit = edited
    project = split.fresh_project(tmp_path / "project")

    delivery = split.session_start(sandbox.root, project)

    assert delivery.text_of(unit) == split.source_text(sandbox.root, unit)


def test_a_whole_recipient_receives_the_edited_rule_whole(
    edited: tuple[Sandbox, split.Unit], tmp_path: Path
) -> None:
    sandbox, unit = edited
    project = split.fresh_project(tmp_path / "project")

    delivery = split.spawn(sandbox.root, project, "general-purpose")

    assert delivery.text_of(unit) == split.source_text(sandbox.root, unit)
