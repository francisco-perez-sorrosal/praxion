"""Every section of every always-loaded source has exactly one audience, or the commit is refused.

The always-loaded sources are the rules without a path scope, the user-level
template and the project instruction file; the set is found from the repository,
so a new unscoped rule is covered without editing a list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_manifest, kernel_sandbox
from tests.acceptance.drivers.audience_manifest import AudienceEntry
from tests.acceptance.drivers.kernel_sandbox import (
    PROJECT_INSTRUCTIONS,
    USER_TEMPLATE,
    Sandbox,
    commit_gate,
)

PROBE_HEADING = "Resident Probe Section"
PROBE_SECTION = f"## {PROBE_HEADING}\n\nA paragraph that no audience entry classifies yet.\n"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def test_the_repository_as_committed_passes_the_kernel_gates_offline(sandbox: Sandbox) -> None:
    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, f"the committed checkout is refused:\n{verdict.output}"


@pytest.mark.parametrize(
    "source",
    ["rules/swe/agent-intermediate-documents.md", USER_TEMPLATE, PROJECT_INSTRUCTIONS],
)
def test_a_new_heading_in_an_always_loaded_source_without_an_entry_is_refused_by_name(
    sandbox: Sandbox, source: str
) -> None:
    sandbox.append(source, PROBE_SECTION)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "an unclassified always-loaded section was let through"
    assert PROBE_HEADING in verdict.output, f"the refusal does not name it:\n{verdict.output}"


def test_the_same_new_heading_with_its_entry_passes(sandbox: Sandbox) -> None:
    source = "rules/swe/agent-intermediate-documents.md"
    sandbox.append(source, PROBE_SECTION)
    audience_manifest.add_entry(
        sandbox.root,
        AudienceEntry(source, PROBE_HEADING, "no-actor", reason="probe text no agent acts on"),
    )

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, f"a classified section was refused:\n{verdict.output}"


def test_a_new_rule_without_a_path_scope_is_covered_without_editing_any_list(
    sandbox: Sandbox,
) -> None:
    sandbox.write(
        "rules/swe/resident-probe.md",
        f"## Resident Probe Rule\n\nAn always-loaded rule.\n\n{PROBE_SECTION}",
    )

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a new unscoped rule's sections were never classified"
    assert "Resident Probe Rule" in verdict.output, verdict.output
    assert PROBE_HEADING in verdict.output, verdict.output


def test_a_new_heading_in_a_path_scoped_rule_needs_no_entry(sandbox: Sandbox) -> None:
    sandbox.append("rules/swe/testing-conventions.md", PROBE_SECTION)

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, f"a path-scoped rule's section was demanded:\n{verdict.output}"


def test_renaming_a_heading_names_the_new_section_and_the_orphaned_entry(
    sandbox: Sandbox,
) -> None:
    sandbox.replace(
        "rules/swe/agent-intermediate-documents.md",
        "### Version Control and Cleanup\n",
        "### Cleanup and Version Control\n",
    )

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a renamed always-loaded heading was let through"
    assert "Cleanup and Version Control" in verdict.output, (
        f"the refusal does not name the unclassified heading:\n{verdict.output}"
    )
    assert "Version Control and Cleanup" in verdict.output, (
        f"the refusal does not name the orphaned entry:\n{verdict.output}"
    )


def test_a_mixed_section_whose_leading_part_has_no_entry_is_refused(sandbox: Sandbox) -> None:
    source = "rules/swe/agent-intermediate-documents.md"
    sandbox.append(
        source,
        f"## {PROBE_HEADING}\n\n"
        "Alpha part: text the orchestrator alone acts on.\n\n"
        "Beta part: text every spawned role acts on.\n",
    )
    audience_manifest.add_entry(
        sandbox.root,
        AudienceEntry(source, PROBE_HEADING, "no-actor", part="Beta part:", reason="probe text"),
    )

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a part of a mixed-audience section went unclassified"
    assert PROBE_HEADING in verdict.output, verdict.output
    assert "Alpha part" in verdict.output, verdict.output


def test_a_mixed_section_with_every_part_classified_passes(sandbox: Sandbox) -> None:
    source = "rules/swe/agent-intermediate-documents.md"
    sandbox.append(
        source,
        f"## {PROBE_HEADING}\n\n"
        "Alpha part: text the orchestrator alone acts on.\n\n"
        "Beta part: text no agent acts on.\n",
    )
    for prefix, scope in (("Alpha part:", "orchestrator-only"), ("Beta part:", "no-actor")):
        audience_manifest.add_entry(
            sandbox.root,
            AudienceEntry(source, PROBE_HEADING, scope, part=prefix, reason="probe text"),
        )

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, f"a fully classified mixed section was refused:\n{verdict.output}"
