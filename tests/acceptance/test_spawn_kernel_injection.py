"""A spawned Praxion role at trial or switched receives its kernel through the spawn hook.

Every scenario runs the registered hooks as separate processes on a synthetic
`SubagentStart` event, against a sandbox copy of the plugin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import kernel_adoption, kernel_sandbox, kernel_spawn
from tests.acceptance.drivers.kernel_sandbox import (
    CONTRACT_RULE,
    INJECTION_CAP,
    PLUGIN_ROOT_VARIABLE,
    Sandbox,
    all_kernel_text,
    normalize_plugin_location,
    paragraphs,
)
from tests.acceptance.drivers.kernel_spawn import kernel_rows, spawn


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return kernel_spawn.project_checkout(tmp_path / "project")


def contract_lines(root: Path) -> list[str]:
    text = (root / CONTRACT_RULE).read_text()
    return [ln for ln in text.splitlines() if ln.startswith("- **")]


def project_instructions(lines: int) -> str:
    return "".join(
        f"Project convention line {i:04d}: keep fixtures under data/.\n" for i in range(lines)
    )


# -- Who receives a kernel -------------------------------------------------------------


@pytest.mark.parametrize("status", ["trial", "switched"])
def test_a_role_at_trial_or_switched_receives_only_committed_kernel_text(
    sandbox: Sandbox, project: Path, status: str
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.AdoptionRecord("verifier", status))

    injection = spawn(sandbox.root, project, "praxion:verifier")
    received = normalize_plugin_location(injection.joined, sandbox.root)
    committed = normalize_plugin_location(all_kernel_text(sandbox.root), sandbox.root)

    assert injection.strings, "the role received no kernel"
    assert [p for p in paragraphs(received) if p not in committed] == []


@pytest.mark.parametrize("role", ["implementer", "systems-architect", "test-engineer"])
def test_a_role_at_no_adoption_status_receives_nothing_at_spawn(
    sandbox: Sandbox, project: Path, role: str
) -> None:
    injection = spawn(sandbox.root, project, f"praxion:{role}")

    assert injection.strings == ()


def test_a_plugin_without_an_adoption_ledger_injects_nothing(
    sandbox: Sandbox, project: Path
) -> None:
    sandbox.path(kernel_sandbox.ADOPTION_LEDGER).unlink(missing_ok=True)

    injection = spawn(sandbox.root, project, "praxion:researcher")

    assert injection.strings == ()


def test_an_adoption_ledger_found_in_the_project_is_never_read(
    sandbox: Sandbox, project: Path
) -> None:
    sandbox.path(kernel_sandbox.ADOPTION_LEDGER).unlink(missing_ok=True)
    kernel_adoption.record(project, kernel_adoption.at_trial("researcher"))

    injection = spawn(sandbox.root, project, "praxion:researcher")

    assert injection.strings == ()


@pytest.mark.parametrize("agent_type", ["Explore", "Plan", "general-purpose"])
def test_a_host_native_agent_receives_no_role_kernel(
    sandbox: Sandbox, project: Path, agent_type: str
) -> None:
    injection = spawn(sandbox.root, project, agent_type)

    assert injection.strings == ()


@pytest.mark.parametrize("agent_type", ["researcher", "other-plugin:researcher"])
def test_an_agent_outside_praxion_sharing_a_role_name_receives_no_role_kernel(
    sandbox: Sandbox, project: Path, agent_type: str
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("researcher"))

    injection = spawn(sandbox.root, project, agent_type)

    assert injection.strings == ()


@pytest.mark.parametrize(
    "stdin",
    ["not json at all", '{"hook_event_name": "SubagentStart"}', '{"agent_type": 7}', ""],
    ids=["not JSON", "no agent type", "agent type not a string", "empty"],
)
def test_malformed_input_never_blocks_or_outlives_the_spawn(
    sandbox: Sandbox, project: Path, stdin: str
) -> None:
    injection = spawn(sandbox.root, project, "praxion:researcher", raw_stdin=stdin)

    assert [e for e in injection.exits if e.exit_code != 0] == []


# -- Size and order ------------------------------------------------------------------


@pytest.mark.parametrize("role", kernel_sandbox.agent_names(kernel_sandbox.REPO_ROOT))
def test_every_injected_string_fits_the_cap_and_the_first_carries_the_contract(
    sandbox: Sandbox, project: Path, role: str
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial(role))

    strings = spawn(sandbox.root, project, f"praxion:{role}").strings

    assert strings, f"{role} received no kernel"
    assert [len(s) for s in strings if len(s) > INJECTION_CAP] == []
    assert [ln for ln in contract_lines(sandbox.root) if ln not in strings[0]] == []


# -- Outside the Praxion checkout ------------------------------------------------------


def test_outside_the_checkout_the_running_plugins_kernel_arrives_with_its_location_written_out(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    project = kernel_spawn.project_checkout(tmp_path / "elsewhere")
    decoy = project / "claude" / "kernels" / "core.md"
    decoy.parent.mkdir(parents=True)
    decoy.write_text("DECOY KERNEL: a project copy that must never be injected.\n")
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("researcher"))

    injected = spawn(sandbox.root, project, "praxion:researcher").joined

    assert injected, "nothing was injected outside the checkout"
    assert "DECOY KERNEL" not in injected
    assert PLUGIN_ROOT_VARIABLE not in injected


def test_the_principles_pointer_leads_to_readable_principle_text_inside_the_plugin(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    project = kernel_spawn.project_checkout(tmp_path / "elsewhere")
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("researcher"))
    injected = spawn(sandbox.root, project, "praxion:researcher").joined
    principles = [
        s.heading
        for s in kernel_sandbox.markdown_sections(sandbox.read(kernel_sandbox.USER_TEMPLATE))
        if s.level == 3
    ][:8]

    readable = [
        p
        for p in sandbox.root.rglob("*.md")
        if str(p) in injected and all(name in p.read_text() for name in principles)
    ]

    assert readable, "no file the kernel names inside the plugin carries the principles"


def test_from_a_subdirectory_the_project_is_found_through_git(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    project = kernel_spawn.project_checkout(tmp_path / "elsewhere")
    inner = project / "src" / "pkg"
    inner.mkdir(parents=True)
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("researcher"))

    spawn(sandbox.root, project, "praxion:researcher", process_cwd=inner)

    assert len(kernel_rows(project)) == 1, "the kernel row did not land at the project root"
    assert kernel_rows(sandbox.root) == [], "the hook used its own location as the project"


# -- The observation log ---------------------------------------------------------------


def test_a_spawn_that_receives_a_kernel_leaves_exactly_one_row_describing_it(
    sandbox: Sandbox, project: Path
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("verifier"))

    strings = spawn(sandbox.root, project, "praxion:verifier").strings
    rows = kernel_rows(project)

    assert len(rows) == 1, rows
    row = kernel_spawn.describe_kernel_row(rows[0])
    assert row.role == "verifier"
    assert row.char_counts == tuple(len(s) for s in strings)
    assert row.parts, "the row names no module or part delivered"
    assert row.kernel_identity, "the row does not identify the kernel version"


def test_a_spawn_that_receives_no_kernel_leaves_no_row(sandbox: Sandbox, project: Path) -> None:
    spawn(sandbox.root, project, "praxion:implementer")

    assert kernel_rows(project) == []


def test_a_switched_role_spawned_without_the_hook_is_reported_by_the_liveness_check(
    sandbox: Sandbox, project: Path
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.switched_without_record("researcher"))
    kernel_spawn.unregister_kernel_hooks(sandbox.root)

    spawn(sandbox.root, project, "praxion:researcher")

    assert kernel_rows(project) == []
    assert "researcher" in kernel_spawn.kernel_liveness_findings(project, sandbox.root)


# -- The project's own instruction file --------------------------------------------------


def test_a_large_project_instruction_file_arrives_whole_in_parts_beside_the_kernel(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    instructions = project_instructions(400)
    project = kernel_spawn.project_checkout(tmp_path / "managed", instructions=instructions)
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("researcher"))

    strings = spawn(sandbox.root, project, "praxion:researcher").strings
    lines = "\n".join(strings).splitlines()
    wanted = instructions.splitlines()

    assert len(instructions) > INJECTION_CAP
    assert [len(s) for s in strings if len(s) > INJECTION_CAP] == []
    assert [ln for ln in lines if ln in set(wanted)] == wanted, (
        "the project's CLAUDE.md did not arrive whole and in order"
    )


def test_a_small_project_instruction_file_arrives_whole(sandbox: Sandbox, tmp_path: Path) -> None:
    instructions = project_instructions(12)
    project = kernel_spawn.project_checkout(tmp_path / "managed", instructions=instructions)
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("verifier"))

    strings = spawn(sandbox.root, project, "praxion:verifier").strings

    assert any(instructions.strip() in s for s in strings)


def test_a_project_without_an_instruction_file_receives_only_kernel_text(
    sandbox: Sandbox, project: Path
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("researcher"))

    received = normalize_plugin_location(
        spawn(sandbox.root, project, "praxion:researcher").joined, sandbox.root
    )
    committed = normalize_plugin_location(all_kernel_text(sandbox.root), sandbox.root)

    assert received, "the role received no kernel"
    assert [p for p in paragraphs(received) if p not in committed] == []
