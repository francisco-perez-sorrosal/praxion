"""A confined kit's session runs the shell work its definition prescribes, in its own sandbox.

The implementer and the verifier run the fixture's test runner, the formatter and the
linter, git reads and the Praxion scripts their definitions name, written as a bare name,
an absolute path into the plugin copy, an inline interpreter call, a chain or with output
redirected into the task's directory; none draws a denial. A script named by its bare name
is the plugin copy's, never an install on the operator's machine; the test runner, the
formatter and the linter are the runner's own. Each fixture repository's tests, run with no
arguments at its root, are all collected and pass. Every check runs at no cost: the grant is
read from the dry run, and the commands run in a sandbox built without a session.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import confined_kits as kits
from tests.acceptance.drivers.confined_kits import (
    CONFINED_ROLES,
    FIXTURE_REPOSITORIES,
    MODULE_ONLY_SCRIPTS,
    NAMED_SCRIPTS,
    TOOLCHAIN,
)

FORMS = [(role, form) for role in CONFINED_ROLES for form in kits.prescribed_forms(role)]
SCRIPTS = [(role, name) for role in CONFINED_ROLES for name in NAMED_SCRIPTS[role]]
RUNNABLE = [(role, name) for role, name in SCRIPTS if name not in MODULE_ONLY_SCRIPTS]


@pytest.fixture(scope="module")
def printed(tmp_path_factory) -> kits.DryRun:
    return kits.dry_run(tmp_path_factory.mktemp("confined-dry-run"), CONFINED_ROLES)


def first_session(printed: kits.DryRun, role: str):
    return next(s for s in printed.sessions if s.role == role)


@pytest.mark.parametrize(("role", "form"), FORMS)
def test_every_prescribed_shell_command_is_granted_without_a_denial(printed, role, form):
    session = first_session(printed, role)
    places = kits.planned_places(session)
    command = kits.fill(form, plugin=places.plugin_copy, slug=places.slug)

    confinement = kits.printed_confinement(session)

    assert confinement is not None, f"the {role}'s session is planned with no confinement"
    assert confinement.approves(command), f"the {role}'s grant denies: {command}"


# -- In a sandbox built for a task ----------------------------------------------------------------


@pytest.mark.parametrize(("role", "script"), SCRIPTS)
def test_a_named_script_resolves_to_the_plugin_copy_before_an_operator_install(
    tmp_path, role, script
):
    decoys = kits.plant_decoys(tmp_path / "operator-install", [s for _, s in SCRIPTS])
    sandbox = kits.materialize(tmp_path / "run", role, operator_path_first=decoys)

    found = kits.resolved(sandbox, script)

    assert found is not None, f"{script} does not resolve in the {role}'s sandbox"
    assert kits.is_within(found, sandbox.plugin_copy), f"{script} resolves to {found}"


@pytest.mark.parametrize(("role", "script"), RUNNABLE)
def test_a_named_script_runs_by_its_bare_name(tmp_path, role, script):
    sandbox = kits.materialize(tmp_path, role)

    ran = kits.run_shell(sandbox, f"{script} --help")

    assert ran.exit_code == 0, f"{script} --help exited {ran.exit_code}: {ran.stderr[-1500:]}"


@pytest.mark.parametrize("role", CONFINED_ROLES)
@pytest.mark.parametrize("program", TOOLCHAIN)
def test_the_toolchain_resolves_from_the_runners_own_environment(tmp_path, role, program):
    sandbox = kits.materialize(tmp_path, role)

    found = kits.resolved(sandbox, program)

    assert found is not None, f"{program} does not resolve in the {role}'s sandbox"
    runner = kits.runner_environment()
    assert kits.is_within(found, runner.prefix) or kits.is_within(found, runner.base_prefix), (
        f"{program} resolves to {found}, outside the runner's environment {runner.prefix}"
    )


@pytest.mark.parametrize(
    "form",
    [
        "python -m pytest -q",
        "pytest -q",
        "python3 -m pytest -q",
        "git status --short && git diff && git log --oneline -1",
        "python3 {plugin}/scripts/check_test_results_shape.py --help",
        "mkdir -p .ai-work/{slug}/logs && python -m pytest -q > .ai-work/{slug}/logs/step-1.log 2>&1",
    ],
)
@pytest.mark.parametrize("role", CONFINED_ROLES)
def test_a_prescribed_command_does_its_work_in_the_sandbox(tmp_path, role, form):
    sandbox = kits.materialize(tmp_path, role)
    command = kits.fill(form, plugin=sandbox.plugin_copy, slug=sandbox.slug)

    ran = kits.run_shell(sandbox, command)

    assert ran.exit_code == 0, f"{command} exited {ran.exit_code}: {ran.stderr[-1500:]}"


def test_the_redirected_test_run_leaves_its_log_in_the_tasks_directory(tmp_path):
    sandbox = kits.materialize(tmp_path, "implementer")
    log = sandbox.scratch / ".ai-work" / sandbox.slug / "logs" / "step-1.log"

    kits.run_shell(sandbox, f"mkdir -p {log.parent} && python -m pytest -q > {log} 2>&1")

    assert "passed" in log.read_text(encoding="utf-8")


def test_the_row_id_function_answers_an_inline_interpreter_call(tmp_path):
    sandbox = kits.materialize(tmp_path, "verifier")
    command = kits.fill(kits.ROLE_FORMS["verifier"][-1], plugin=sandbox.plugin_copy, slug="x")

    ran = kits.run_shell(sandbox, command)

    assert ran.exit_code == 0, ran.stderr[-1500:]
    assert ran.stdout.strip(), "the row-id function printed nothing"


@pytest.mark.parametrize("role", CONFINED_ROLES)
def test_the_linter_and_the_formatter_run_over_the_fixture(tmp_path, role):
    sandbox = kits.materialize(tmp_path, role)

    ran = kits.run_shell(sandbox, "ruff format . && ruff check .")

    assert ran.found_its_program, ran.stderr[-1500:]
    assert ran.exit_code in (0, 1), f"ruff could not run: {ran.stderr[-1500:]}"


# -- The fixtures' own tests -------------------------------------------------------------------


@pytest.mark.parametrize("fixture", FIXTURE_REPOSITORIES)
@pytest.mark.parametrize("role", CONFINED_ROLES)
def test_the_fixtures_tests_run_with_no_arguments_at_its_root_and_pass(tmp_path, role, fixture):
    run = kits.fixture_test_run(tmp_path, role, fixture)

    assert run.exit_code == 0, f"{run.task_id}: pytest exited {run.exit_code}\n{run.output[-2000:]}"


@pytest.mark.parametrize("fixture", FIXTURE_REPOSITORIES)
@pytest.mark.parametrize("role", CONFINED_ROLES)
def test_the_fixtures_tests_are_every_one_collected(tmp_path, role, fixture):
    run = kits.fixture_test_run(tmp_path, role, fixture)

    assert run.collected_files() == set(run.test_files), run.output[-2000:]
