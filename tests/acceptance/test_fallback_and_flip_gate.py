"""Without the hook every agent keeps today's blocks; a role is switched only on its full record.

The three universal blocks stay in every definition, generated from the kernel
core; `omitClaudeMd` lands on a pilot role only with its adoption record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import (
    kernel_adoption,
    kernel_sandbox,
    kernel_spawn,
    resident_sections,
)
from tests.acceptance.drivers.kernel_sandbox import (
    PILOT_ROLES,
    REPO_ROOT,
    UNIVERSAL_BLOCKS,
    Sandbox,
    agent_path,
    canonical_block,
    commit_gate,
    frontmatter,
    module_text,
    normalize_plugin_location,
    regenerate,
    shared_blocks_gate,
    universal_block_carriers,
)

OMIT = "omitClaudeMd: true"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


# -- The fallback --------------------------------------------------------------------------


def test_with_the_hook_unregistered_every_definition_still_carries_the_universal_blocks(
    sandbox: Sandbox,
) -> None:
    kernel_spawn.unregister_kernel_hooks(sandbox.root)

    verdict = shared_blocks_gate(sandbox.root)
    definitions, carriers = universal_block_carriers(sandbox.root)

    assert not verdict.refused, verdict.output
    assert carriers == dict.fromkeys(UNIVERSAL_BLOCKS, definitions)


def flagged_without_switch(root: Path) -> list[str]:
    flagged = [
        name
        for name in kernel_sandbox.agent_names(root)
        if frontmatter((root / agent_path(name)).read_text()).get("omitClaudeMd")
    ]
    return [name for name in flagged if name not in kernel_adoption.switched_roles(root)]


def test_no_role_short_of_switched_stops_inheriting_its_instruction_files() -> None:
    assert flagged_without_switch(REPO_ROOT) == []


@pytest.mark.parametrize("slug", UNIVERSAL_BLOCKS)
def test_each_universal_block_is_the_kernel_cores_own_text(slug: str) -> None:
    block = normalize_plugin_location(canonical_block(REPO_ROOT, slug), REPO_ROOT)

    assert block in normalize_plugin_location(module_text(REPO_ROOT, "core"), REPO_ROOT)


@pytest.mark.parametrize("slug", UNIVERSAL_BLOCKS)
def test_a_one_word_edit_to_a_universal_block_in_a_definition_is_refused(
    sandbox: Sandbox, slug: str
) -> None:
    block = canonical_block(sandbox.root, slug)
    words = block.split(" ")
    edited = " ".join([*words[:5], "reworded", *words[6:]])
    sandbox.replace(agent_path("verifier"), block, edited)

    verdict = shared_blocks_gate(sandbox.root)

    assert verdict.refused, f"an edited {slug} block was let through"


@pytest.mark.parametrize("slug", UNIVERSAL_BLOCKS)
def test_a_definition_missing_a_universal_block_is_refused(sandbox: Sandbox, slug: str) -> None:
    sandbox.replace(agent_path("researcher"), canonical_block(sandbox.root, slug), "")

    verdict = shared_blocks_gate(sandbox.root)

    assert verdict.refused, f"a definition without its {slug} block was let through"


@pytest.mark.parametrize("role", PILOT_ROLES)
def test_a_switched_definition_differs_from_before_only_by_the_flag_and_its_blocks(
    role: str,
) -> None:
    text = (REPO_ROOT / agent_path(role)).read_text()
    blocks = [canonical_block(REPO_ROOT, slug) for slug in UNIVERSAL_BLOCKS]
    frozen = resident_sections.load("pilot_definitions.json")[role]
    unflagged = "omitClaudeMd" not in frontmatter(text)

    current = resident_sections.digest(resident_sections.definition_without_blocks(text, blocks))

    assert unflagged or current == frozen, f"{role} changed beyond its flag and blocks"


# -- The flip gate -------------------------------------------------------------------------


def test_omit_claude_md_on_a_role_outside_the_pilot_is_refused(sandbox: Sandbox) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.full_switch_record("implementer"))
    kernel_sandbox.set_frontmatter_key(sandbox, "implementer", OMIT)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a non-pilot role was switched"
    assert "implementer" in verdict.output, verdict.output


@pytest.mark.parametrize("element", kernel_adoption.MISSING_ELEMENTS)
def test_omit_claude_md_on_a_pilot_role_without_its_full_record_is_refused(
    sandbox: Sandbox, element: str
) -> None:
    record = kernel_adoption.lacking(kernel_adoption.full_switch_record("researcher"), element)
    kernel_adoption.record(sandbox.root, record)
    kernel_sandbox.set_frontmatter_key(sandbox, "researcher", OMIT)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, f"researcher was switched with {element}"
    assert "researcher" in verdict.output, verdict.output


@pytest.mark.parametrize("role", PILOT_ROLES)
def test_omit_claude_md_on_a_pilot_role_with_its_full_record_passes(
    sandbox: Sandbox, role: str
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.full_switch_record(role))
    kernel_sandbox.set_frontmatter_key(sandbox, role, OMIT)
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output
