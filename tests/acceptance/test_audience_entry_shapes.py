"""An audience entry is one of the legal shapes; every illegal one is refused by name."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_manifest, kernel_sandbox
from tests.acceptance.drivers.audience_manifest import (
    ADR_AUTHORS,
    CURRENT_PIN,
    AudienceEntry,
)
from tests.acceptance.drivers.kernel_sandbox import Sandbox, commit_gate, regenerate

SOURCE = "rules/swe/agent-intermediate-documents.md"
HEADING = "Audience Shape Probe"
PROBE = f"## {HEADING}\n\nA probe paragraph whose audience the scenario decides.\n"
CONDENSED = "A condensed probe paragraph."


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    sb = kernel_sandbox.new_sandbox(template, tmp_path / "plugin")
    sb.append(SOURCE, PROBE)
    return sb


def entry(scope: str, **fields: object) -> AudienceEntry:
    return AudienceEntry(SOURCE, HEADING, scope, **fields)


ILLEGAL_SHAPES = {
    "an empty audience": entry(""),
    "an unknown scope": entry("everyone", reason="probe"),
    "a role entry naming no agent or group": entry("role", form="verbatim"),
    "a role entry naming an unknown agent": entry(
        "role", agents=("no-such-agent",), form="verbatim"
    ),
    "a role entry naming an unknown group": entry(
        "role", groups=("no-such-group",), form="verbatim"
    ),
    "a core entry without a form": entry("core"),
    "a condensed entry without a pin": entry("core", form="condensed", condensed_text=CONDENSED),
    "an orchestrator-only entry without a reason": entry("orchestrator-only"),
    "a no-actor entry without a reason": entry("no-actor", reason=""),
    "an orchestrator-only entry naming an agent": entry(
        "orchestrator-only", reason="probe", agents=("researcher",)
    ),
    "a no-actor entry naming an agent": entry("no-actor", reason="probe", agents=("verifier",)),
}


@pytest.mark.parametrize("shape", list(ILLEGAL_SHAPES))
def test_an_illegal_entry_shape_is_refused_naming_the_entry(sandbox: Sandbox, shape: str) -> None:
    audience_manifest.add_entry(sandbox.root, ILLEGAL_SHAPES[shape])

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, f"{shape} was accepted"
    assert HEADING in verdict.output, (
        f"the refusal of {shape} does not name the entry:\n{verdict.output}"
    )


def test_two_entries_for_one_section_are_refused(sandbox: Sandbox) -> None:
    audience_manifest.add_entry(sandbox.root, entry("no-actor", reason="probe"))
    audience_manifest.add_entry(sandbox.root, entry("orchestrator-only", reason="probe"))

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a section with two audiences was accepted"
    assert HEADING in verdict.output, f"the refusal does not name the section:\n{verdict.output}"


def test_a_group_with_no_members_is_refused(sandbox: Sandbox) -> None:
    audience_manifest.declare_group(sandbox.root, "probe-group", ())
    audience_manifest.add_entry(
        sandbox.root, entry("role", groups=("probe-group",), form="verbatim")
    )

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "an entry for an empty group was accepted"
    assert "probe-group" in verdict.output or HEADING in verdict.output, (
        f"the refusal names neither the entry nor the group:\n{verdict.output}"
    )


def test_a_pin_that_no_longer_matches_its_source_is_refused(sandbox: Sandbox) -> None:
    audience_manifest.add_entry(
        sandbox.root,
        entry(
            "role",
            agents=("researcher",),
            form="condensed",
            condensed_text=CONDENSED,
            pin=CURRENT_PIN,
        ),
    )
    regenerate(sandbox.root)
    sandbox.replace(SOURCE, "A probe paragraph whose", "A reworded probe paragraph whose")

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a condensed entry kept a stale pin"
    assert HEADING in verdict.output, f"the refusal does not name the entry:\n{verdict.output}"


LEGAL_SHAPES = {
    "core, verbatim": entry("core", form="verbatim"),
    "core, condensed with its pin": entry(
        "core", form="condensed", condensed_text=CONDENSED, pin=CURRENT_PIN
    ),
    "role for an agent, verbatim": entry("role", agents=("researcher",), form="verbatim"),
    "role for a declared group, verbatim": entry("role", groups=(ADR_AUTHORS,), form="verbatim"),
    "role for an agent, condensed with its pin": entry(
        "role", agents=("verifier",), form="condensed", condensed_text=CONDENSED, pin=CURRENT_PIN
    ),
    "orchestrator-only with a reason": entry("orchestrator-only", reason="the main session's"),
    "no-actor with a reason": entry("no-actor", reason="a note for maintainers"),
}


@pytest.mark.parametrize("shape", list(LEGAL_SHAPES))
def test_a_legal_entry_shape_is_accepted(sandbox: Sandbox, shape: str) -> None:
    audience_manifest.add_entry(sandbox.root, LEGAL_SHAPES[shape])
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, f"{shape} was refused:\n{verdict.output}"
