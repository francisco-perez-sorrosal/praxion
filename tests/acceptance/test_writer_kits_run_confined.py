"""A writer role's shell work runs under the confined-kit contract, and does its work.

Every planned session of the test-engineer and the systems-architect shows a confinement that
is required, with no unconfined fallback or retry; a confined command carries no session
credential, reads neither the session token file nor an operator credential location, writes
nowhere outside its sandbox nor into the plugin copy, and opens no network connection. Every
shell command the role's definition prescribes in a covered mode is let through. In a sandbox
built for a task, the Praxion scripts the definition names resolve to the plugin copy and run,
and the test runner, git reads and the record-id hash do their work. Nothing here starts a
model session.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import adherence_eval, confined_kits
from tests.acceptance.drivers import writer_kits as kits
from tests.acceptance.drivers.confined_kits import SESSION_CREDENTIALS
from tests.acceptance.drivers.writer_kits import NAMED_SCRIPTS, WRITER_ROLES

CREDENTIAL_LOCATIONS = (
    ".ssh/id_ed25519",
    ".aws/credentials",
    ".config/gh/hosts.yml",
    ".netrc",
    ".claude.json",
    ".claude/.credentials.json",
)
HOSTS = ("example.com", "github.com", "pypi.org", "api.anthropic.com", "localhost")
FORMS = [(role, mode, form) for role in WRITER_ROLES for mode, form in kits.prescribed(role)]
SCRIPTS = [(role, script) for role in WRITER_ROLES for script in NAMED_SCRIPTS[role]]


@pytest.fixture(scope="module")
def operator_token(tmp_path_factory):
    token_file, _ = kits.write_token_file(tmp_path_factory.mktemp("operator"))
    return token_file


@pytest.fixture(scope="module")
def printed(tmp_path_factory, operator_token) -> dict[str, kits.Plan]:
    workspace = tmp_path_factory.mktemp("writer-confined")
    return {
        role: kits.plan(workspace / role, role, token_file=operator_token) for role in WRITER_ROLES
    }


@pytest.fixture(scope="module", params=WRITER_ROLES)
def session(request, printed):
    return printed[request.param].sessions[0]


def confinement_of(session) -> confined_kits.Confinement:
    found = confined_kits.printed_confinement(session)
    assert found is not None, f"the {session.role}'s session is planned with no confinement"
    return found


# -- What every planned session shows ------------------------------------------------------------


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_every_planned_session_of_a_writer_role_shows_a_confinement(printed, role):
    unconfined = [
        (s.arm, s.task_id)
        for s in printed[role].sessions
        if confined_kits.printed_confinement(s) is None
    ]

    assert printed[role].sessions, f"the {role}'s dry run planned no session"
    assert unconfined == [], f"the {role}'s sessions planned unconfined: {unconfined[:4]}"


def test_a_session_that_cannot_start_confined_does_not_start_and_is_never_retried_unconfined(
    session,
):
    confinement = confinement_of(session)

    assert confinement.required
    assert not confinement.unconfined_fallback
    assert not confinement.unconfined_retry


def test_a_confined_command_starts_with_no_session_credential(session):
    assert set(SESSION_CREDENTIALS) <= confinement_of(session).shell_env_drops


def test_the_session_token_file_is_unreadable_by_every_path_that_reaches_it(
    session, operator_token
):
    confinement = confinement_of(session)
    spellings = {
        str(operator_token),
        str(operator_token.resolve()),
        str(operator_token.parent / "." / operator_token.name),
    }

    readable = sorted(path for path in spellings if not confinement.read_refused(path))

    assert readable == [], f"the session token file is readable as: {readable}"


@pytest.mark.parametrize("location", CREDENTIAL_LOCATIONS)
def test_an_operator_credential_location_is_unreadable_to_a_confined_command(session, location):
    assert confinement_of(session).read_refused(str(confined_kits.real_home() / location))


@pytest.mark.parametrize("host", HOSTS)
def test_a_confined_command_opens_no_network_connection(session, host):
    assert confinement_of(session).network_refused(host)


def test_a_confined_command_cannot_write_into_the_plugin_copy(session):
    confinement = confinement_of(session)
    places = confined_kits.planned_places(session)

    assert confinement.write_refused(str(places.plugin_copy / "agents" / f"{session.role}.md"))
    assert confinement.write_refused(str(places.plugin_copy / "scripts" / "extract_spec.py"))


def test_a_confined_command_cannot_write_outside_its_sandbox(session):
    confinement = confinement_of(session)
    outside = (confined_kits.real_home() / ".zshrc", adherence_eval.REPO_ROOT / "README.md")

    let_through = [str(p) for p in outside if not confinement.write_refused(str(p))]

    assert let_through == [], f"writes let through outside the sandbox: {let_through}"


def test_a_confined_command_writes_inside_its_sandbox(session):
    confinement = confinement_of(session)
    places = confined_kits.planned_places(session)

    assert not confinement.write_refused(str(places.scratch / "tests" / "test_new.py"))
    assert not confinement.write_refused(str(places.scratch / ".ai-work" / places.slug / "x.md"))


@pytest.mark.parametrize(("role", "mode", "form"), FORMS)
def test_every_prescribed_shell_command_is_let_through(printed, role, mode, form):
    session = printed[role].sessions[0]
    places = confined_kits.planned_places(session)
    command = confined_kits.fill(form, plugin=places.plugin_copy, slug=places.slug)

    confinement = confinement_of(session)

    assert confinement.approves(command), f"the {role}'s grant refuses ({mode}): {command}"


# -- In a sandbox built for a task ---------------------------------------------------------------


@pytest.fixture(scope="module")
def sandboxes(tmp_path_factory) -> dict[str, confined_kits.MaterializedSandbox]:
    return {
        role: confined_kits.materialize(tmp_path_factory.mktemp(f"{role}-sandbox"), role)
        for role in WRITER_ROLES
    }


@pytest.mark.parametrize(("role", "script"), SCRIPTS)
def test_a_named_script_resolves_to_the_plugin_copy_and_runs(sandboxes, role, script):
    sandbox = sandboxes[role]

    found = confined_kits.resolved(sandbox, script)
    ran = confined_kits.run_shell(sandbox, f"{script} --help")

    assert found is not None, f"{script} does not resolve in the {role}'s sandbox"
    assert confined_kits.is_within(found, sandbox.plugin_copy), f"{script} resolves to {found}"
    assert ran.exit_code == 0, f"{script} --help exited {ran.exit_code}: {ran.stderr[-1000:]}"


def test_the_test_engineers_test_run_leaves_its_log_in_the_tasks_directory(sandboxes):
    sandbox = sandboxes["test-engineer"]
    log = sandbox.scratch / ".ai-work" / sandbox.slug / "logs" / "step-1.log"

    ran = confined_kits.run_shell(
        sandbox, f"mkdir -p {log.parent} && python3 -m pytest -q --tb=short -rf > {log} 2>&1"
    )

    assert ran.exit_code == 0, log.read_text(encoding="utf-8")[-1500:]
    assert "passed" in log.read_text(encoding="utf-8")


def test_the_test_engineers_formatter_and_linter_run_over_the_tests(sandboxes):
    ran = confined_kits.run_shell(
        sandboxes["test-engineer"], "ruff format tests && ruff check tests"
    )

    assert ran.found_its_program, ran.stderr[-1500:]
    assert ran.exit_code in (0, 1), f"ruff could not run: {ran.stderr[-1500:]}"


def test_the_test_engineers_base_commit_reads_answer(sandboxes):
    ran = confined_kits.run_shell(
        sandboxes["test-engineer"],
        "git show HEAD:pyproject.toml > /dev/null && git diff --quiet HEAD -- pyproject.toml",
    )

    assert ran.exit_code == 0, ran.stderr[-1500:]


def test_the_architects_git_reads_name_the_branch_a_record_is_filed_under(sandboxes):
    ran = confined_kits.run_shell(sandboxes["systems-architect"], "git rev-parse --abbrev-ref HEAD")

    assert ran.exit_code == 0, ran.stderr[-1500:]
    assert ran.stdout.strip(), "the branch read printed nothing"


def test_the_architects_record_id_hash_prints_eight_hex_digits(sandboxes):
    sandbox = sandboxes["systems-architect"]
    form = kits.PRESCRIBED_FORMS["systems-architect"]["feature"][-1]

    ran = confined_kits.run_shell(sandbox, form)

    assert ran.exit_code == 0, ran.stderr[-1500:]
    assert re.fullmatch(r"[0-9a-f]{8}", ran.stdout.strip()), ran.stdout
