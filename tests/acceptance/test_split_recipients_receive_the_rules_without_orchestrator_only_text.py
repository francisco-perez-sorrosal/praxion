"""A spawn of one of this plugin's inheriting roles receives the two process rules without the
text the audience manifest addresses to the main session alone.

Every scenario runs the registered hooks as separate processes on a synthetic `SubagentStart`
event in a managed project, and compares what arrives with the split text computed from the
rule's own source and the audience manifest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_split as split
from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers.audience_split import (
    ADR_RESIDENT,
    CORE_UNITS,
    INTERMEDIATE,
    PROTOCOL,
    REPO_ROOT,
    SPLIT_ROLES,
    SPLIT_UNITS,
)
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


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
@pytest.mark.parametrize("role", SPLIT_ROLES)
def test_a_split_recipient_receives_each_rule_as_its_split_text(
    project: Path, role: str, unit: split.Unit
) -> None:
    delivery = split.spawn(REPO_ROOT, project, f"praxion:{role}")

    assert delivery.text_of(unit) == split.split_text(REPO_ROOT, unit)


@pytest.mark.parametrize("unit", SPLIT_UNITS, ids=lambda u: u.id)
def test_no_orchestrator_only_section_heading_reaches_a_split_recipient(
    project: Path, unit: split.Unit
) -> None:
    received = split.spawn(REPO_ROOT, project, "praxion:verifier").text_of(unit) or ""
    received_lines = received.splitlines()

    leaked = [
        h
        for h in split.dropped_headings(REPO_ROOT, unit)
        if any(ln.endswith(f"# {h}") for ln in received_lines)
    ]

    assert leaked == [], f"orchestrator-only sections of {unit.id} reached a split recipient"


def test_a_section_losing_only_some_parts_keeps_its_heading_and_its_kept_part(
    project: Path,
) -> None:
    received = split.spawn(REPO_ROOT, project, "praxion:verifier").text_of(PROTOCOL) or ""

    assert "### Proactive Agent Usage\n" in received
    assert "**Multiplicity check:**" in received
    assert "Spawn agents without waiting" not in received


def test_the_adr_resident_arrives_whole_after_the_two_rules(project: Path) -> None:
    delivery = split.spawn(REPO_ROOT, project, "praxion:verifier")

    assert delivery.unit_order() == [u.id for u in CORE_UNITS]
    assert delivery.text_of(ADR_RESIDENT) == split.source_text(REPO_ROOT, ADR_RESIDENT)


@pytest.mark.parametrize("role", SPLIT_ROLES)
def test_what_a_split_recipient_receives_does_not_depend_on_its_role(
    project: Path, role: str
) -> None:
    reference = split.spawn(REPO_ROOT, project, "praxion:verifier")

    delivery = split.spawn(REPO_ROOT, project, f"praxion:{role}")

    assert delivery.rule_strings == reference.rule_strings


@pytest.mark.parametrize(
    "spelling", ["omitClaudeMd: True", "omitClaudeMd: yes", 'omitClaudeMd: "true"']
)
def test_a_role_spelling_the_lean_flag_other_than_literal_true_is_a_split_recipient(
    sandbox: Sandbox, project: Path, spelling: str
) -> None:
    kernel_sandbox.set_frontmatter_key(sandbox, "verifier", spelling)

    delivery = split.spawn(sandbox.root, project, "praxion:verifier")

    assert delivery.text_of(PROTOCOL) == split.split_text(sandbox.root, PROTOCOL)
    assert delivery.text_of(INTERMEDIATE) == split.split_text(sandbox.root, INTERMEDIATE)


def test_a_project_blacklist_naming_the_core_rules_leaves_a_split_recipient_its_split_text(
    project: Path,
) -> None:
    split.write_blacklist(project, [u.id for u in CORE_UNITS])

    delivery = split.spawn(REPO_ROOT, project, "praxion:verifier")

    assert delivery.unit_order() == [u.id for u in CORE_UNITS]
    assert delivery.text_of(PROTOCOL) == split.split_text(REPO_ROOT, PROTOCOL)
    assert delivery.text_of(INTERMEDIATE) == split.split_text(REPO_ROOT, INTERMEDIATE)
