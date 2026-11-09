"""For each rule, a split recipient receives exactly the split text of the current source and
audience manifest, or the whole unit as the base delivered it, and never anything else; under
the impaired floor it still receives all three managed core units, each string within the
harness's inline limit and none left unprinted.

Each scenario damages or edits a sandbox copy of the plugin, then reads a split recipient's
delivery against the split text computed from that copy and against the base commit's hooks
delivering the same copy (the whole unit).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_split as split
from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers.audience_split import (
    ADR_RESIDENT,
    AUDIENCE_MANIFEST,
    CORE_UNITS,
    IMPAIRMENTS,
    INLINE_CAP,
    PLANTS,
    SOURCE_ONLY_PLANTS,
    SPLIT_UNITS,
)
from tests.acceptance.drivers.kernel_sandbox import Sandbox

pytestmark = pytest.mark.skipif(
    not split.base_commit_available(),
    reason=f"the base commit {split.BASE_COMMIT} is not in this clone's history (shallow clone); "
    "fetch full history to compare against the whole unit as the base delivered it",
)

ACCEPTABLE = {"split", "whole"}
SPLIT_RECIPIENT = "praxion:verifier"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def _readings(
    sandbox: Sandbox, tmp_path: Path, env: dict | None = None, *, base: Path | None = None
):
    """(what a split recipient receives, what the base's hooks deliver it) for the sandbox now."""
    base = base or split.base_hooks_arm(sandbox.root, tmp_path / "base-plugin")
    readings = []
    for plugin_root in (sandbox.root, base):
        project = split.fresh_project(tmp_path / "project")
        readings.append(
            split.spawn(
                plugin_root, project, SPLIT_RECIPIENT, scratch=tmp_path / "scratch", env=env
            )
        )
    return tuple(readings)


# -- A damaged audience manifest or split input -----------------------------------------------

DAMAGE = ("missing", "garbage", "truncated")
DAMAGED_FILES = sorted({AUDIENCE_MANIFEST, *split.changed_data_files()})


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
@pytest.mark.parametrize("how", DAMAGE)
@pytest.mark.parametrize("rel", DAMAGED_FILES)
def test_a_damaged_split_input_leaves_each_rule_split_or_whole(
    sandbox: Sandbox, tmp_path: Path, rel: str, how: str, unit: split.Unit
) -> None:
    split.damage(sandbox, rel, how)

    received, whole = _readings(sandbox, tmp_path)

    assert split.delivered_as(received, whole, sandbox.root, unit) in ACCEPTABLE


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_an_unreadable_audience_manifest_leaves_each_rule_whole(
    sandbox: Sandbox, tmp_path: Path, unit: split.Unit
) -> None:
    base = split.base_hooks_arm(sandbox.root, tmp_path / "base-plugin")
    split.unreadable(sandbox.path(AUDIENCE_MANIFEST))

    received, whole = _readings(sandbox, tmp_path, base=base)

    assert split.delivered_as(received, whole, sandbox.root, unit) == "whole"


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_an_audience_manifest_of_the_wrong_shape_leaves_each_rule_whole(
    sandbox: Sandbox, tmp_path: Path, unit: split.Unit
) -> None:
    sandbox.write(AUDIENCE_MANIFEST, "version: 1\nentries: 7\n")

    received, whole = _readings(sandbox, tmp_path)

    assert split.delivered_as(received, whole, sandbox.root, unit) == "whole"


# -- A source or classification changed after the split was taken -------------------------------


@pytest.mark.parametrize("name", PLANTS)
def test_an_edited_rule_or_classification_arrives_split_for_the_current_tree_or_whole(
    sandbox: Sandbox, tmp_path: Path, name: str
) -> None:
    touched = split.plant(sandbox, name)

    received, whole = _readings(sandbox, tmp_path)

    assert split.delivered_as(received, whole, sandbox.root, touched) in ACCEPTABLE


@pytest.mark.parametrize("name", SOURCE_ONLY_PLANTS)
def test_the_rule_an_edit_did_not_touch_still_arrives_as_its_split_text(
    sandbox: Sandbox, tmp_path: Path, name: str
) -> None:
    untouched = split.other_unit(split.plant(sandbox, name))

    received, whole = _readings(sandbox, tmp_path)

    assert split.delivered_as(received, whole, sandbox.root, untouched) == "split"


# -- The impaired floor -------------------------------------------------------------------------


@pytest.mark.parametrize("impairment", IMPAIRMENTS)
def test_an_impaired_split_recipient_still_receives_the_three_core_units_in_order(
    sandbox: Sandbox, tmp_path: Path, impairment: str
) -> None:
    base = split.base_hooks_arm(sandbox.root, tmp_path / "base-plugin")
    split.impair(base, tmp_path / "scratch", impairment)
    env = split.impair(sandbox.root, tmp_path / "scratch", impairment)

    received, whole = _readings(sandbox, tmp_path, env, base=base)

    assert received.unit_order() == [u.id for u in CORE_UNITS]
    assert split.delivered_as(received, whole, sandbox.root, ADR_RESIDENT) == "whole"
    assert [
        split.delivered_as(received, whole, sandbox.root, u) in ACCEPTABLE for u in SPLIT_UNITS
    ] == [True, True]


@pytest.mark.parametrize("impairment", IMPAIRMENTS)
def test_an_impaired_split_recipient_in_an_unmanaged_scope_receives_no_rule_text(
    sandbox: Sandbox, tmp_path: Path, impairment: str
) -> None:
    env = split.impair(sandbox.root, tmp_path / "scratch", impairment)
    project = split.fresh_project(tmp_path / "project", managed=False)

    received = split.spawn(
        sandbox.root, project, SPLIT_RECIPIENT, scratch=tmp_path / "scratch", env=env
    )

    assert received.rule_strings == ()


# -- Every planned string fits and arrives --------------------------------------------------------

RECIPIENTS = (SPLIT_RECIPIENT, "general-purpose")


@pytest.mark.parametrize("impairment", ["unimpaired", *IMPAIRMENTS])
@pytest.mark.parametrize("agent_type", RECIPIENTS)
def test_every_rule_string_a_spawn_receives_is_within_the_inline_limit(
    sandbox: Sandbox, tmp_path: Path, agent_type: str, impairment: str
) -> None:
    env = split.impair(sandbox.root, tmp_path / "scratch", impairment)
    project = split.fresh_project(tmp_path / "project")

    received = split.spawn(sandbox.root, project, agent_type, scratch=tmp_path / "scratch", env=env)

    assert [len(s) for s in received.rule_strings if len(s) > INLINE_CAP] == []


@pytest.mark.parametrize("impairment", ["unimpaired", *IMPAIRMENTS])
@pytest.mark.parametrize("agent_type", RECIPIENTS)
def test_every_part_a_label_announces_reaches_the_spawn_once_and_in_order(
    sandbox: Sandbox, tmp_path: Path, agent_type: str, impairment: str
) -> None:
    env = split.impair(sandbox.root, tmp_path / "scratch", impairment)
    project = split.fresh_project(tmp_path / "project")

    received = split.spawn(sandbox.root, project, agent_type, scratch=tmp_path / "scratch", env=env)

    assert received.labels() == received.announced()
