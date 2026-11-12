"""Standing on the Shoulders of Giants sits in the philosophy and reaches the roles that choose.

Presence checks: the kernel, drift, parity and export gates already guard how text travels, so
each surface the principle must reach is checked once, where its reader meets it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.acceptance.drivers import (
    audience_manifest,
    kernel_adoption,
    kernel_sandbox,
    kernel_spawn,
)
from tests.acceptance.drivers import principle_names as names
from tests.acceptance.drivers.kernel_sandbox import (
    REPO_ROOT,
    USER_TEMPLATE,
    Sandbox,
    agent_path,
    missing_paragraphs,
    normalize_plugin_location,
    section_body,
)

PRINCIPLE = "Standing on the Shoulders of Giants"
CHOOSING_ROLES = ("promethean", "systems-architect", "researcher")
CODEX_TEMPLATE = "codex/config/AGENTS.md.tmpl"
CODEX_BASELINE_START = "<!-- PRAXION:PROJECT_BASELINE:START -->"
CODEX_BASELINE_END = "<!-- PRAXION:PROJECT_BASELINE:END -->"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def received(sandbox: Sandbox, project: Path, role: str) -> str:
    """What `role` holds at spawn: its injected kernel plus its own definition."""
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial(role))
    injection = kernel_spawn.spawn(sandbox.root, project, f"praxion:{role}")
    definition = sandbox.read(agent_path(role))
    return normalize_plugin_location(injection.joined + "\n\n" + definition, sandbox.root)


def principle_text(root: Path) -> str:
    return section_body((root / USER_TEMPLATE).read_text(encoding="utf-8"), PRINCIPLE)


# -- The philosophy ----------------------------------------------------------------------------


def test_the_principle_sits_between_data_structures_first_and_incremental_evolution() -> None:
    headings = names.template_headings(REPO_ROOT)

    assert PRINCIPLE in headings, f"the template's principles are {headings}"
    at = headings.index(PRINCIPLE)
    assert headings[at - 1 : at + 2] == [
        "Data Structures First",
        PRINCIPLE,
        "Incremental Evolution",
    ]
    assert principle_text(REPO_ROOT).strip(), "the principle's heading carries no text"


# -- The three choosing roles ------------------------------------------------------------------


@pytest.mark.parametrize("role", CHOOSING_ROLES)
def test_a_choosing_role_receives_the_principles_full_text_at_spawn(
    sandbox: Sandbox, tmp_path: Path, role: str
) -> None:
    project = kernel_spawn.project_checkout(tmp_path / "project")

    holds = received(sandbox, project, role)

    assert missing_paragraphs(principle_text(sandbox.root), holds) == [], (
        f"the {role} lacks the principle's text"
    )


def test_the_audience_manifest_delivers_the_principle_verbatim_to_the_three_roles_alone() -> None:
    found = [
        (e.scope, e.form, set(e.agents).union(*map(audience_of_group, e.groups)))
        for e in audience_manifest.entries(REPO_ROOT)
        if e.source == USER_TEMPLATE and e.heading == PRINCIPLE
    ]

    assert found == [("role", "verbatim", set(CHOOSING_ROLES))]


def audience_of_group(group: str) -> set[str]:
    return set(audience_manifest.group_members(REPO_ROOT, group))


def test_the_kernel_manifest_check_passes_on_this_checkout(tmp_path: Path) -> None:
    result = kernel_sandbox._run(
        [sys.executable, "scripts/check_kernel_manifest.py"],
        REPO_ROOT,
        kernel_sandbox.isolated_env(tmp_path),
    )

    assert result.exit_code == 0, result.output[-3000:]


# -- The other assistants ------------------------------------------------------------------------


def test_the_codex_project_baseline_carries_the_principle_among_its_principles() -> None:
    text = (REPO_ROOT / CODEX_TEMPLATE).read_text(encoding="utf-8")
    baseline = text.split(CODEX_BASELINE_START, 1)[1].split(CODEX_BASELINE_END, 1)[0]

    assert PRINCIPLE in names.principle_headings(baseline)
