"""The commit-time kernel checks refuse a tree at which a split recipient would receive anything
other than the split text of that tree's sources and audience manifest, a fallback to the whole
unit included, and name the rule that disagrees; on a tree where the delivery agrees they pass.

Each scenario reads, on a sandbox copy of the plugin, what a split recipient receives and the
verdict of the `.pre-commit-config.yaml` hooks that run the kernel checkers, and holds the two
to each other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_split as split
from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers.audience_split import AUDIENCE_MANIFEST, PLANTS
from tests.acceptance.drivers.kernel_sandbox import Sandbox


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return split.fresh_project(tmp_path / "project")


def test_the_checks_verdict_on_this_checkout_agrees_with_what_a_split_recipient_receives(
    sandbox: Sandbox, project: Path
) -> None:
    reading = split.drift_reading(sandbox, project)

    assert (reading.refused, reading.named) == (bool(reading.disagreeing), reading.disagreeing), (
        reading.output
    )


@pytest.mark.parametrize("name", PLANTS)
def test_a_planted_disagreement_is_refused_naming_its_rule_and_an_agreement_passes(
    sandbox: Sandbox, project: Path, name: str
) -> None:
    split.plant(sandbox, name)

    reading = split.drift_reading(sandbox, project)

    assert (reading.refused, reading.named) == (bool(reading.disagreeing), reading.disagreeing), (
        reading.output
    )


@pytest.mark.parametrize("name", PLANTS)
def test_a_checkout_restored_after_a_plant_delivers_the_split_and_passes(
    sandbox: Sandbox, project: Path, name: str
) -> None:
    before = split.snapshot(sandbox)
    split.plant(sandbox, name)
    split.restore(sandbox, before)

    reading = split.drift_reading(sandbox, project)

    assert (reading.disagreeing, reading.refused) == ((), False), reading.output


@pytest.mark.parametrize("how", ["missing", "garbage", "truncated"])
@pytest.mark.parametrize("rel", sorted({AUDIENCE_MANIFEST, *split.changed_data_files()}))
def test_a_damaged_split_input_that_makes_a_spawn_fall_back_is_refused(
    sandbox: Sandbox, project: Path, rel: str, how: str
) -> None:
    split.damage(sandbox, rel, how)

    reading = split.drift_reading(sandbox, project)

    assert reading.refused or not reading.disagreeing, (
        f"a split recipient receives {reading.disagreeing} other than as split text, "
        f"yet the kernel checks pass:\n{reading.output}"
    )
