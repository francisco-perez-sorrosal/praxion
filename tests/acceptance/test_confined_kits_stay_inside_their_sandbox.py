"""A confined kit's shell reaches no further than its sandbox, and the dry run shows how.

Each planned session of the implementer's and the verifier's kits shows, at no cost, the
confinement it would be started with: required, with no unconfined fallback and no
unconfined retry, commands inside it approved without a prompt, and the order it resolves
programs in. A confined command writes nowhere outside the task's sandbox, never into the
plugin copy, and opens no network connection; it reads neither the session token file, by
any path that reaches it, nor the operator's credentials, nor anything of the real home
beyond the runner's environment, its interpreter, the plugin copy and the run root; and its
environment carries no session credential, while the session's own environment is as before.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers import confined_kits as kits
from tests.acceptance.drivers.confined_kits import CONFINED_ROLES, SESSION_CREDENTIALS

CREDENTIAL_LOCATIONS = (
    ".ssh/id_ed25519",
    ".ssh/config",
    ".aws/credentials",
    ".config/gcloud/application_default_credentials.json",
    ".azure/accessTokens.json",
    ".npmrc",
    ".pypirc",
    ".cargo/credentials.toml",
    ".config/gh/hosts.yml",
    ".netrc",
    ".claude.json",
    ".claude/settings.json",
    ".claude/.credentials.json",
)
HOSTS = ("example.com", "github.com", "pypi.org", "api.anthropic.com", "localhost")


@pytest.fixture(scope="module")
def printed(tmp_path_factory) -> kits.DryRun:
    workspace = tmp_path_factory.mktemp("confined-dry-run")
    token = kits.write_token_file(workspace / "operator-token")
    return kits.dry_run(workspace, CONFINED_ROLES, token_file=token)


@pytest.fixture(scope="module", params=CONFINED_ROLES)
def session(request, printed):
    return next(s for s in printed.sessions if s.role == request.param)


def confinement_of(session) -> kits.Confinement:
    found = kits.printed_confinement(session)
    assert found is not None, f"the {session.role}'s session is planned with no confinement"
    return found


# -- What the dry run shows ---------------------------------------------------------------------


def test_the_dry_run_shows_a_confinement_for_every_planned_session_of_a_confined_kit(printed):
    unconfined = [
        (s.role, s.arm, s.task_id) for s in printed.sessions if kits.printed_confinement(s) is None
    ]

    assert {s.role for s in printed.sessions} == set(CONFINED_ROLES)
    assert {s.arm for s in printed.sessions} == set(adherence_eval.ARMS)
    assert unconfined == [], f"planned sessions with no confinement: {unconfined[:5]}"


def test_the_dry_run_of_a_confined_kit_starts_no_model_session(printed):
    assert printed.started_sessions == 0


def test_the_confinement_is_required_with_no_unconfined_fallback_or_retry(session):
    confinement = confinement_of(session)
    assert confinement.required
    assert not confinement.unconfined_fallback
    assert not confinement.unconfined_retry


def test_commands_inside_the_confinement_run_without_a_prompt(session):
    confinement = confinement_of(session)
    assert confinement.approves_without_prompt


def test_programs_resolve_from_the_plugin_copy_before_the_operators_path(session):
    confinement = confinement_of(session)
    places = kits.planned_places(session)
    order = list(confinement.program_order)
    plugin_dirs = [i for i, d in enumerate(order) if d.startswith(str(places.plugin_copy))]

    assert plugin_dirs, f"no directory of the plugin copy is on the program order: {order}"
    assert plugin_dirs[0] == 0, f"a directory resolves ahead of the plugin copy's: {order}"


# -- Writes and the network ----------------------------------------------------------------------


def test_a_write_inside_the_sandbox_is_let_through(session):
    confinement = confinement_of(session)
    places = kits.planned_places(session)

    assert not confinement.write_refused(str(places.scratch / "src" / "change.py"))
    assert not confinement.write_refused(str(places.tmp / "scratch.txt"))


def test_a_write_into_the_plugin_copy_is_refused(session):
    confinement = confinement_of(session)
    places = kits.planned_places(session)

    assert confinement.write_refused(str(places.plugin_copy / "agents" / f"{session.role}.md"))
    assert confinement.write_refused(str(places.plugin_copy / "scripts" / "extract_spec.py"))


def test_a_write_outside_the_sandbox_is_refused(printed, session):
    confinement = confinement_of(session)
    outside = (
        printed.checkout / "README.md",
        kits.real_home() / ".zshrc",
        adherence_eval.REPO_ROOT / "README.md",
    )

    refused = {str(path): confinement.write_refused(str(path)) for path in outside}

    assert all(refused.values()), f"writes let through outside the sandbox: {refused}"


@pytest.mark.parametrize("host", HOSTS)
def test_a_network_connection_is_refused(session, host):
    confinement = confinement_of(session)
    assert confinement.network_refused(host)


# -- Reads of the operator's files ----------------------------------------------------------------


def test_the_session_token_file_is_unreadable_by_every_path_that_reaches_it(session, printed):
    confinement = confinement_of(session)
    token = printed.token_file
    spellings = {str(token), str(token.resolve()), str(token.parent / "." / token.name)}

    readable = [path for path in spellings if not confinement.read_refused(path)]

    assert readable == [], f"the session token file is readable as: {readable}"


@pytest.mark.parametrize("location", CREDENTIAL_LOCATIONS)
def test_an_operator_credential_location_in_the_real_home_is_unreadable(session, location):
    confinement = confinement_of(session)
    assert confinement.read_refused(str(kits.real_home() / location))


def test_the_real_home_is_readable_only_where_a_session_needs_it(session):
    confinement = confinement_of(session)
    places = kits.planned_places(session)
    runner = kits.runner_environment()
    needed = (
        runner.prefix / "pyvenv.cfg",
        runner.interpreter,
        places.plugin_copy / "agents" / f"{session.role}.md",
        places.run_root / "results.json",
    )

    refused = [str(path) for path in needed if confinement.read_refused(str(path))]

    assert refused == [], f"reads a session needs are refused: {refused}"


def test_the_real_home_beyond_what_a_session_needs_is_unreadable(session):
    confinement = confinement_of(session)
    home = kits.real_home()
    beyond = (home / "Documents" / "notes.txt", home / ".profile", home / "projects" / "app.py")

    readable = [str(path) for path in beyond if not confinement.read_refused(str(path))]

    assert readable == [], f"paths of the real home a confined command may read: {readable}"


def test_a_sibling_of_the_runners_environment_in_the_real_home_is_unreadable(session):
    confinement = confinement_of(session)
    runner = kits.runner_environment()
    if not kits.is_within(runner.prefix, kits.real_home()):
        pytest.skip("the runner's environment is outside the real home on this machine")

    assert confinement.read_refused(str(adherence_eval.REPO_ROOT / "README.md"))


# -- Environments ------------------------------------------------------------------------------


def test_a_confined_command_starts_with_no_session_credential(session):
    confinement = confinement_of(session)
    assert set(SESSION_CREDENTIALS) <= confinement.shell_env_drops


def test_the_sessions_own_environment_is_the_one_it_had_before(printed):
    recorded = kits.frozen_with_token_file()

    changed = {
        (s.role, s.arm): sorted(s.env_names ^ set(recorded[s.role][s.arm]))
        for s in printed.sessions
        if s.env_names != set(recorded[s.role][s.arm])
    }

    assert changed == {}, f"session environment names that changed: {changed}"
