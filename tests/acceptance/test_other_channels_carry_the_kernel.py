"""Host-native agents, Codex and Cursor keep their own deterministic channels.

The host-native preamble keeps today's shape and bound with its contract wording
derived from the core; Codex wrappers embed the role's kernel; the Cursor export
does not change.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import kernel_sandbox, kernel_spawn, resident_sections
from tests.acceptance.drivers.kernel_sandbox import (
    CONTRACT_RULE,
    PLUGIN_ROOT_VARIABLE,
    REPO_ROOT,
    Sandbox,
    codex_instructions,
    commit_gate,
    export_codex,
    module_text,
    normalize_plugin_location,
    paragraphs,
    regenerate,
)

CONTRACT_NAMES = ("Surface Assumptions", "Register Objection", "Stay Surgical", "Simplicity First")
# The contract sentence the Codex exporter wrote separately before this change.
SEPARATE_CONTRACT_SENTENCE = (
    "Also apply the Praxion behavioral contract: Surface Assumptions, Register Objection, "
    "Stay Surgical, Simplicity First."
)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


@pytest.fixture
def managed_project(tmp_path: Path) -> Path:
    return kernel_spawn.project_checkout(tmp_path / "managed")


# -- The host-native preamble -----------------------------------------------------------


@pytest.mark.parametrize("agent_type", ["Explore", "Plan", "general-purpose"])
def test_a_host_native_agent_still_gets_the_short_preamble_within_todays_bound(
    managed_project: Path, agent_type: str
) -> None:
    text = kernel_spawn.preamble(REPO_ROOT, managed_project, agent_type)
    bound = resident_sections.load("host_native_preamble.json")["bound_chars"]

    assert text is not None, "no preamble reached a host-native agent"
    assert len(text) <= bound, f"{len(text)} characters against today's {bound}"
    assert all(name in text for name in CONTRACT_NAMES), text
    assert "pointer, not a payload" in text, text


def test_the_preamble_takes_its_contract_wording_from_the_regenerated_core(
    sandbox: Sandbox, managed_project: Path
) -> None:
    sandbox.replace(CONTRACT_RULE, "**Stay Surgical**", "**Stay Precise**")
    regenerate(sandbox.root)

    text = kernel_spawn.preamble(sandbox.root, managed_project, "Explore")

    assert text is not None, "no preamble reached the host-native agent"
    assert "Stay Precise" in text, text
    assert "Stay Surgical" not in text, text


def test_a_contract_change_without_regenerating_is_refused(sandbox: Sandbox) -> None:
    sandbox.replace(CONTRACT_RULE, "**Stay Surgical**", "**Stay Precise**")

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "a contract change with stale derived text was let through"


# -- Codex wrappers -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wrappers(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    out = tmp_path_factory.mktemp("codex") / "agents"
    return {name: codex_instructions(text) for name, text in export_codex(REPO_ROOT, out).items()}


@pytest.mark.parametrize("role", kernel_sandbox.agent_names(REPO_ROOT))
def test_every_codex_wrapper_embeds_the_core_its_definition_does_not_carry(
    wrappers: dict[str, str], role: str
) -> None:
    instructions = normalize_plugin_location(wrappers[role], REPO_ROOT)
    definition = (REPO_ROOT / kernel_sandbox.agent_path(role)).read_text()
    core = normalize_plugin_location(module_text(REPO_ROOT, "core"), REPO_ROOT)

    absent = [
        p
        for p in paragraphs(core)
        if p not in instructions and p not in normalize_plugin_location(definition, REPO_ROOT)
    ]

    assert absent == [], f"the {role} wrapper lacks core text"


def test_the_verifier_wrapper_embeds_the_verifiers_own_modules(wrappers: dict[str, str]) -> None:
    instructions = normalize_plugin_location(wrappers["verifier"], REPO_ROOT)
    modules = "\n\n".join(
        module_text(REPO_ROOT, m) for m in ("ledger-writer", "principles-anchor", "adr-reader")
    )

    absent = [
        p
        for p in paragraphs(normalize_plugin_location(modules, REPO_ROOT))
        if p not in instructions
    ]

    assert absent == []


@pytest.mark.parametrize("role", kernel_sandbox.agent_names(REPO_ROOT))
def test_no_codex_wrapper_needs_plugin_root_substitution_or_writes_the_contract_separately(
    wrappers: dict[str, str], role: str
) -> None:
    assert PLUGIN_ROOT_VARIABLE not in wrappers[role]
    assert SEPARATE_CONTRACT_SENTENCE not in wrappers[role]


def test_a_definition_exports_to_codex_identically_with_or_without_omit_claude_md(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    before = export_codex(sandbox.root, tmp_path / "without")["researcher"]
    kernel_sandbox.set_frontmatter_key(sandbox, "researcher", "omitClaudeMd: true")

    after = export_codex(sandbox.root, tmp_path / "with")["researcher"]

    assert "omitClaudeMd" not in after
    assert after == before


# -- Cursor --------------------------------------------------------------------------------


def test_the_cursor_export_is_byte_identical_to_before_the_change(tmp_path: Path) -> None:
    frozen = resident_sections.load("cursor_export.json")

    exported = kernel_sandbox.export_cursor(REPO_ROOT, tmp_path / "cursor")

    assert {rel: resident_sections.digest(data) for rel, data in exported.items()} == frozen
