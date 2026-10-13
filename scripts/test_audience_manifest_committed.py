"""Tests for the committed audience manifest, `rules/_audience.yaml`, over the real sources.

The manifest is data a gate will hold to the repository; these tests hold the data itself
to what the repository says today: it loads as legal values, classifies every section and
part of every always-loaded source, pins every condensed text to the bytes it stands for,
and declares the two writer groups as the agent definitions describe them. Each check over
the real files is paired with a canary over the same pure function, so a check that
stopped biting would fail here rather than pass over nothing.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_model as km  # noqa: E402
import kernel_sources as ks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTHORED_DIR = "claude/kernels/src"
CONTRACT_RULE = "rules/swe/agent-behavioral-contract.md"
USER_TEMPLATE = ks.USER_TEMPLATE
ANCHORED_PRINCIPLES = ("Incremental Evolution", "Balanced Coupling")
PILOT_ROLES = (
    "researcher",
    "verifier",
    "discipline-consultant",
    "skill-genesis",
    "context-engineer",
)


@pytest.fixture(scope="module")
def definitions() -> dict[str, str]:
    return km.agent_definitions(REPO_ROOT)


@pytest.fixture(scope="module")
def manifest(definitions: dict[str, str]) -> km.Manifest:
    return km.load_manifest(REPO_ROOT, definitions)


@pytest.fixture(scope="module")
def required() -> tuple[str, ...]:
    return ks.always_loaded_sources(REPO_ROOT)


@pytest.fixture(scope="module")
def sections(required: tuple[str, ...]) -> dict[str, tuple[ks.Section, ...]]:
    return {source: ks.load_sections(REPO_ROOT, source) for source in required}


def _role_modules(manifest: km.Manifest, source: str, heading: str) -> list[str]:
    return [
        entry.scope.module
        for entry in manifest.entries
        if isinstance(entry.scope, km.Role)
        and (entry.target.source, entry.target.heading) == (source, heading)
    ]


def _withheld(manifest: km.Manifest) -> list[tuple[str, str]]:
    """(heading, reason) of each entry kept out of every kernel."""
    return [
        (entry.target.heading, entry.scope.reason)
        for entry in manifest.entries
        if isinstance(entry.scope, km.OrchestratorOnly | km.NoActor)
    ]


def _without_entry_for(manifest: km.Manifest, heading: str) -> km.Manifest:
    kept = tuple(e for e in manifest.entries if e.target.heading != heading)
    return dataclasses.replace(manifest, entries=kept)


# -- The manifest as a legal value -------------------------------------------------------


def test_the_committed_manifest_loads_as_legal_values(manifest: km.Manifest) -> None:
    assert manifest.entries, "the manifest classifies nothing"
    assert {"adr-author", "ledger-writer"} <= set(manifest.groups)


def test_every_group_member_and_module_audience_is_an_agent_or_a_declared_group(
    manifest: km.Manifest, definitions: dict[str, str]
) -> None:
    names = set(definitions) | set(manifest.groups)
    members = [m for group in manifest.groups.values() for m in group]
    audiences = [a for audience in manifest.modules.values() for a in audience]

    unknown = [name for name in (*members, *audiences) if name not in names]

    assert unknown == []


# -- Totality over the real sources --------------------------------------------------------


def test_every_section_and_part_has_an_entry_and_no_entry_is_orphaned(
    manifest: km.Manifest, sections: dict[str, tuple[ks.Section, ...]], required: tuple[str, ...]
) -> None:
    findings = km.check_totality(manifest, sections, required)

    assert findings == (), "\n".join(f"{f.kind}: {f.subject} {f.detail}" for f in findings)


def test_the_set_of_always_loaded_sources_is_the_rules_the_template_and_the_project_file(
    required: tuple[str, ...],
) -> None:
    assert ks.USER_TEMPLATE in required
    assert ks.PROJECT_INSTRUCTIONS in required
    assert CONTRACT_RULE in required


def test_the_totality_check_names_a_section_whose_entry_is_dropped(
    manifest: km.Manifest, sections: dict[str, tuple[ks.Section, ...]], required: tuple[str, ...]
) -> None:
    findings = km.check_totality(_without_entry_for(manifest, "File Format"), sections, required)

    assert [(f.kind, f.subject) for f in findings] == [
        ("unclassified", "rules/swe/adr-conventions.md 'File Format'")
    ]


def test_the_totality_check_names_an_entry_whose_heading_is_gone(
    manifest: km.Manifest, sections: dict[str, tuple[ks.Section, ...]], required: tuple[str, ...]
) -> None:
    renamed = {
        source: tuple(
            dataclasses.replace(s, heading="Renamed Away") if s.heading == "Examples" else s
            for s in found
        )
        for source, found in sections.items()
    }

    findings = km.check_totality(manifest, renamed, required)

    assert {(f.kind, f.subject) for f in findings} == {
        ("unclassified", "rules/swe/vcs/git-conventions.md 'Renamed Away'"),
        ("orphan", "rules/swe/vcs/git-conventions.md 'Examples'"),
    }


# -- Pins, groups and authored texts -----------------------------------------------------------


def test_every_condensed_pin_matches_its_source(
    manifest: km.Manifest, sections: dict[str, tuple[ks.Section, ...]]
) -> None:
    condensed = [e for e in manifest.entries if isinstance(e.form, km.Condensed)]

    assert condensed, "no entry is condensed, so no pin was checked"
    assert km.stale_pins(manifest, sections) == ()


def test_a_source_edited_after_it_was_condensed_is_reported_stale(
    manifest: km.Manifest, sections: dict[str, tuple[ks.Section, ...]]
) -> None:
    source = "rules/swe/swe-agent-coordination-protocol.md"
    edited = {
        **sections,
        source: tuple(
            dataclasses.replace(s, text=s.text + "An added sentence.\n")
            if s.heading == "Delegation Depth"
            else s
            for s in sections[source]
        ),
    }

    stale = km.stale_pins(manifest, edited)

    assert [f.subject for f in stale] == [f"{source} 'Delegation Depth'"]


def test_the_two_writer_groups_equal_the_agents_whose_definitions_write(
    manifest: km.Manifest, definitions: dict[str, str]
) -> None:
    assert km.group_coherence(manifest.groups, definitions) == ()
    assert "verifier" in manifest.groups[km.LEDGER_WRITER]
    assert "verifier" not in manifest.groups[km.ADR_AUTHOR]


@pytest.mark.parametrize(
    ("group", "change", "kind"),
    [
        (km.ADR_AUTHOR, "add researcher", "group-extra"),
        (km.ADR_AUTHOR, "drop systems-architect", "group-missing"),
        (km.LEDGER_WRITER, "add researcher", "group-extra"),
        (km.LEDGER_WRITER, "drop verifier", "group-missing"),
    ],
)
def test_a_group_that_disagrees_with_the_definitions_is_reported_both_ways(
    manifest: km.Manifest, definitions: dict[str, str], group: str, change: str, kind: str
) -> None:
    verb, agent = change.split()
    members = set(manifest.groups[group])
    changed = members | {agent} if verb == "add" else members - {agent}

    findings = km.group_coherence({**manifest.groups, group: tuple(changed)}, definitions)

    assert [(f.kind, f.subject) for f in findings] == [(kind, f"group {group}")]


def test_every_authored_text_is_registered_and_every_registered_path_exists(
    manifest: km.Manifest,
) -> None:
    on_disk = {p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / AUTHORED_DIR).glob("*.md")}
    registered = {text.path for text in manifest.authored}

    assert registered == on_disk


def test_every_authored_text_serves_a_module_that_has_an_audience(manifest: km.Manifest) -> None:
    modules = {km.CORE, *manifest.modules}

    unserved = [t.id for t in manifest.authored if t.module not in modules]

    assert unserved == []


# -- Who receives what, for the pilot roles ----------------------------------------------------


def test_the_verifier_anchors_to_the_two_principles_it_cites_in_a_module_of_its_own(
    manifest: km.Manifest,
) -> None:
    modules = [_role_modules(manifest, USER_TEMPLATE, name) for name in ANCHORED_PRINCIPLES]

    assert modules == [["principles-anchor"], ["principles-anchor"]]
    assert manifest.modules["principles-anchor"] == ("verifier",)


def test_the_discovery_protocol_reaches_the_researcher_and_the_verifier_only(
    manifest: km.Manifest,
) -> None:
    modules = _role_modules(manifest, "rules/swe/adr-conventions.md", "Discovery Protocol")

    assert modules == ["adr-reader"]
    assert set(manifest.modules["adr-reader"]) == {"researcher", "verifier"}


def test_the_context_engineer_alone_has_a_text_of_its_own(manifest: km.Manifest) -> None:
    own = {t.id: t.module for t in manifest.authored if t.module.startswith("local-")}

    assert own["audit-subject-exemption"] == "local-context-engineer"
    assert manifest.modules["local-context-engineer"] == ("context-engineer",)


def test_the_core_carries_the_contract_span_and_withholds_its_tail(manifest: km.Manifest) -> None:
    by_prefix = {
        e.target.prefix: type(e.scope).__name__
        for e in manifest.entries
        if isinstance(e.target, km.PartTarget) and e.target.source == CONTRACT_RULE
    }

    assert by_prefix == {
        "The Methodology defines the flow": "OrchestratorOnly",
        "- **Surface Assumptions**": "Core",
        "No AI authorship in commit messages": "OrchestratorOnly",
    }


def test_every_pilot_role_is_a_known_agent_so_the_kernel_can_be_built_for_it(
    definitions: dict[str, str],
) -> None:
    assert set(PILOT_ROLES) <= set(definitions)


def test_the_manifest_withholds_text_and_gives_each_withheld_entry_a_reason(
    manifest: km.Manifest,
) -> None:
    withheld = _withheld(manifest)

    assert withheld, "nothing is withheld from the kernels"
    assert [heading for heading, reason in withheld if not reason.strip()] == []
