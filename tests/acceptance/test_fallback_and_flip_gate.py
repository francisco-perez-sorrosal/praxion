"""Without the hook every agent keeps today's blocks; a role is switched only on its full record.

The three universal blocks stay in every definition, generated from the kernel
core; `omitClaudeMd` lands on a pilot role only with its adoption record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import (
    flip_gate,
    kernel_adoption,
    kernel_sandbox,
    kernel_spawn,
    resident_sections,
)
from tests.acceptance.drivers.kernel_adoption import AdoptionRecord
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
    kernel_adoption.record(
        sandbox.root, flip_gate.cited_switch_record(sandbox.root, "systems-architect")
    )
    kernel_sandbox.set_frontmatter_key(sandbox, "systems-architect", OMIT)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a role outside the eligible ones was switched"
    assert "systems-architect" in verdict.output, verdict.output


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
    flip_gate.switch_with_flag(sandbox, flip_gate.cited_switch_record(sandbox.root, role))
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output


# -- The ledger's moves --------------------------------------------------------------------

ROLE = "verifier"
TWO_RUNS = kernel_adoption.runs_of(ROLE, 2)
FIRST, SECOND = TWO_RUNS
Runs = tuple[kernel_adoption.AdherenceRun, ...]


def at_trial(runs: Runs = TWO_RUNS, since: str = kernel_adoption.TRIAL_SINCE) -> AdoptionRecord:
    return AdoptionRecord(ROLE, "trial", runs=runs, since=since)


def held(runs: Runs = TWO_RUNS, reason: str | None = kernel_adoption.HELD_REASON) -> AdoptionRecord:
    return kernel_adoption.held(ROLE, runs=runs, reason=reason)


@pytest.mark.parametrize("runs", [(), TWO_RUNS], ids=["no runs", "two runs"])
def test_a_trial_closed_as_held_with_a_reason_passes(sandbox: Sandbox, runs: Runs) -> None:
    kernel_adoption.move(sandbox.root, ROLE, at_trial(runs), held(runs))

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output


def test_a_held_role_reopened_as_a_new_trial_passes(sandbox: Sandbox) -> None:
    kernel_adoption.commit_hold(sandbox.root, held())
    kernel_adoption.rewrite(sandbox.root, at_trial(since=kernel_adoption.reopened_now()))

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output


REOPENED_WITHOUT_EVERY_RUN = {"a run dropped": (SECOND,), "runs reordered": (SECOND, FIRST)}


@pytest.mark.parametrize(
    "runs", REOPENED_WITHOUT_EVERY_RUN.values(), ids=REOPENED_WITHOUT_EVERY_RUN.keys()
)
def test_a_held_role_reopened_without_every_run_in_order_is_refused(
    sandbox: Sandbox, runs: Runs
) -> None:
    kernel_adoption.commit_hold(sandbox.root, held())
    kernel_adoption.rewrite(sandbox.root, at_trial(runs=runs, since=kernel_adoption.reopened_now()))

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a re-opened trial lost or reordered the runs its hold kept"
    assert ROLE in verdict.output, verdict.output


@pytest.mark.parametrize("start", kernel_adoption.STARTS_OUT_OF_BOUNDS)
def test_a_held_role_reopened_with_its_start_out_of_bounds_is_refused(
    sandbox: Sandbox, start: str
) -> None:
    kernel_adoption.commit_hold(sandbox.root, held())
    kernel_adoption.rewrite(
        sandbox.root, at_trial(since=kernel_adoption.start_out_of_bounds(start))
    )

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, f"a re-opened trial with {start} was let through"
    assert ROLE in verdict.output, verdict.output


def test_a_held_role_flipped_straight_to_switched_is_refused(sandbox: Sandbox) -> None:
    switch = kernel_adoption.full_switch_record(ROLE)
    kernel_adoption.move(sandbox.root, ROLE, held(runs=switch.runs), switch)
    kernel_sandbox.set_frontmatter_key(sandbox, ROLE, OMIT)
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a held role was switched without a new trial"
    assert ROLE in verdict.output, verdict.output


# Each move: the role's record at the parent commit, then the record the commit under
# test leaves; None is no record (absent before, removed after).
REFUSED_MOVES = {
    "held with no reason": (at_trial(), held(reason=None)),
    "held with an empty reason": (at_trial(), held(reason="")),
    "a run dropped from a trial": (at_trial(), at_trial(runs=(FIRST,))),
    "a run dropped from a held record": (held(), held(runs=(SECOND,))),
    "runs reordered": (at_trial(), at_trial(runs=(SECOND, FIRST))),
    "a run added to a held record": (held(runs=(FIRST,)), held()),
    "the record removed": (at_trial(), None),
    "no status straight to held": (None, held()),
}


@pytest.mark.parametrize(("before", "after"), REFUSED_MOVES.values(), ids=REFUSED_MOVES.keys())
def test_a_ledger_move_outside_the_rule_is_refused_naming_the_role(
    sandbox: Sandbox, before: AdoptionRecord | None, after: AdoptionRecord | None
) -> None:
    kernel_adoption.move(sandbox.root, ROLE, before, after)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "the gate let the move through"
    assert ROLE in verdict.output, verdict.output
