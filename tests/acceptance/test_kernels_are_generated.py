"""Kernels are generated, committed, fresh, within the cap, and the core carries the shared process."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_manifest, kernel_sandbox
from tests.acceptance.drivers.audience_manifest import AudienceEntry
from tests.acceptance.drivers.kernel_sandbox import (
    CONTRACT_RULE,
    INJECTION_CAP,
    REPO_ROOT,
    Sandbox,
    commit_gate,
    generate_kernels,
    kernel_files,
    module_parts,
    module_text,
    regenerate,
)

USER_FILE_SENTENCE = (
    "The user-level instruction file is not loaded for you and must not be sought as "
    "instructions; your kernel carries what you need from it."
)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def contract_lines(root: Path) -> list[str]:
    """The contract rule's four behavior bullets and its self-test, as the rule words them."""
    text = (root / CONTRACT_RULE).read_text()
    return [ln for ln in text.splitlines() if ln.startswith("- **") or ln.startswith("Self-test:")]


# -- Generated, committed, fresh ----------------------------------------------------


def test_generating_twice_from_the_same_sources_yields_identical_kernels(sandbox: Sandbox) -> None:
    regenerate(sandbox.root)
    first = kernel_files(sandbox.root)
    regenerate(sandbox.root)

    assert kernel_files(sandbox.root) == first


def test_the_committed_kernels_are_what_the_committed_sources_produce(sandbox: Sandbox) -> None:
    committed = kernel_files(sandbox.root)

    regenerate(sandbox.root)

    assert kernel_files(sandbox.root) == committed, "the committed kernels are stale"


def test_a_one_word_edit_to_a_verbatim_source_is_refused_until_regenerated(
    sandbox: Sandbox,
) -> None:
    sandbox.replace(
        CONTRACT_RULE, "state your interpretation upfront", "state your reading upfront"
    )

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a kernel stale against its verbatim source was let through"


def test_the_same_edit_passes_once_the_kernels_are_regenerated(sandbox: Sandbox) -> None:
    sandbox.replace(
        CONTRACT_RULE, "state your interpretation upfront", "state your reading upfront"
    )
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, f"regenerated kernels were refused:\n{verdict.output}"
    assert "state your reading upfront" in module_text(sandbox.root, "core")


def test_the_committed_agent_definitions_are_what_the_generator_derives(sandbox: Sandbox) -> None:
    definitions = {
        name: sandbox.read(kernel_sandbox.agent_path(name))
        for name in kernel_sandbox.agent_names(sandbox.root)
    }

    regenerate(sandbox.root)

    changed = [
        name
        for name, text in definitions.items()
        if sandbox.read(kernel_sandbox.agent_path(name)) != text
    ]
    assert changed == [], f"the generator rewrote the universal blocks of {changed}"


def test_the_generator_refuses_nothing_on_the_committed_sources(sandbox: Sandbox) -> None:
    result = generate_kernels(sandbox.root)

    assert result.exit_code == 0, result.output


# -- The size cap ---------------------------------------------------------------------


def test_every_committed_kernel_file_fits_one_injected_string() -> None:
    sizes = {name: len(text) for name, text in kernel_files(REPO_ROOT).items()}

    assert all(size <= INJECTION_CAP for size in sizes.values()), f"over the cap: {sizes}"


def test_a_module_padded_past_the_cap_arrives_as_ordered_parts_that_rebuild_it(
    sandbox: Sandbox,
) -> None:
    padding = "\n\n".join(f"Padding paragraph {i:03d}: " + "core text " * 12 for i in range(100))
    sandbox.append(CONTRACT_RULE, f"## Core Padding Probe\n\n{padding}\n")
    audience_manifest.add_entry(
        sandbox.root, AudienceEntry(CONTRACT_RULE, "Core Padding Probe", "core", form="verbatim")
    )
    regenerate(sandbox.root)

    parts = module_parts(sandbox.root, "core")

    assert len(parts) >= 2, "a core above the cap was not split into numbered parts"
    assert all(len(p) <= INJECTION_CAP for p in parts), [len(p) for p in parts]
    assert padding in "".join(parts), "the parts do not concatenate back to the module"
    assert all(line in parts[0] for line in contract_lines(sandbox.root)), (
        "the behavioral contract is not in the core's first part"
    )


# -- What the core carries --------------------------------------------------------------


def test_the_core_carries_the_contract_behaviors_and_self_test_word_for_word() -> None:
    core = module_text(REPO_ROOT, "core")

    missing = [line for line in contract_lines(REPO_ROOT) if line not in core]

    assert missing == [], f"the core lacks, or rewords, {missing}"


def test_the_core_carries_the_user_file_sentence_verbatim() -> None:
    assert USER_FILE_SENTENCE in module_text(REPO_ROOT, "core")


@pytest.mark.parametrize(
    "item",
    [
        "[COMPLETE]",
        "[BLOCKED]",
        "[CONFLICT]",
        "[PARTIAL]",
        "Completed phases",
        "Stopped at",
        "Usable sections",
        ".ai-work/",
        ".ai-state/",
    ],
)
def test_the_core_carries_the_shared_process_item(item: str) -> None:
    assert item in module_text(REPO_ROOT, "core"), f"the core does not carry {item!r}"


@pytest.mark.parametrize(
    "pattern",
    [r"\bdec-\d{2,}", r"\bREQ-\d+", r"\b20\d\d-\d\d-\d\d"],
    ids=["decision record number", "requirement id", "dated state file"],
)
def test_no_kernel_names_a_dated_or_numbered_record(pattern: str) -> None:
    found = {
        name: re.findall(pattern, text)
        for name, text in kernel_files(REPO_ROOT).items()
        if re.search(pattern, text)
    }

    assert found == {}, f"kernels name {found}"


def test_a_core_without_the_contract_is_refused(sandbox: Sandbox) -> None:
    audience_manifest.reclassify(
        sandbox.root,
        AudienceEntry(CONTRACT_RULE, "Agent Behavioral Contract", "no-actor", reason="probe"),
    )
    generate_kernels(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a core without the behavioral contract was let through"
