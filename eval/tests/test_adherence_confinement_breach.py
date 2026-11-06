"""A confined kit's broken confinement is read from its session's record: the three signals,
the commands a definition prescribes (in every form it gives them), and the roles that never
break a confinement they do not hold."""

from __future__ import annotations

from typing import get_args

import pytest

from praxion_evals.adherence.confinement import (
    CONFINED_ROLES,
    EVIDENCE_CHARS,
    PRESCRIBED_COMMANDS,
    ShellRun,
    confinement_breach,
    refused_prescribed,
)
from praxion_evals.adherence.infra_stop import COUNTING_KINDS
from praxion_evals.adherence.model import ERROR_KINDS, Errored, RefusedCommand, Role
from praxion_evals.adherence.session_loop import RETRYABLE_ERRORS

SANDBOX_REFUSAL = "Sandbox is required but failed to initialize: seatbelt denied"
STARTUP_STDERR = "Error: sandbox required by settings (failIfUnavailable) but unavailable."
COPY = "/work/run/plugin"
OTHER_ROLES = sorted(set(get_args(Role)) - CONFINED_ROLES)


def _refused(command: str, source="permission_denials") -> RefusedCommand:
    return RefusedCommand(command, source)


def _breach(
    role: Role = "verifier",
    *,
    refused=(),
    results=(),
    stderr="",
    started=True,
    runs=(),
) -> str | None:
    return confinement_breach(role, tuple(refused), tuple(results), stderr, started, tuple(runs))


# -- The error kind --------------------------------------------------------------------------------


def test_the_confinement_error_kind_is_an_errored_kind_that_neither_counts_nor_retries():
    assert Errored("confinement_broken", "evidence").kind in ERROR_KINDS
    assert "confinement_broken" not in COUNTING_KINDS
    assert "confinement_broken" not in RETRYABLE_ERRORS


# -- The three signals, each alone ------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(CONFINED_ROLES))
def test_a_session_that_never_started_and_whose_stderr_names_the_sandbox_is_broken(role):
    evidence = _breach(role, stderr=STARTUP_STDERR, started=False)

    assert evidence is not None
    assert STARTUP_STDERR in evidence


@pytest.mark.parametrize("stderr", ["SANDBOX unavailable", "the Sandbox could not start"])
def test_the_startup_signal_matches_the_sandbox_in_any_case(stderr):
    assert _breach(stderr=stderr, started=False) is not None


@pytest.mark.parametrize(
    ("stderr", "started"),
    [
        ("connection reset by peer", False),
        ("", False),
        (STARTUP_STDERR, True),
    ],
    ids=["stderr-silent-on-the-sandbox", "no-stderr", "session-started"],
)
def test_a_startup_exit_is_read_only_from_a_session_without_init_that_names_the_sandbox(
    stderr, started
):
    assert _breach(stderr=stderr, started=started) is None


@pytest.mark.parametrize("role", sorted(CONFINED_ROLES))
def test_the_sandbox_refusal_in_a_tool_result_is_broken(role):
    evidence = _breach(role, results=["ok", f"Error: {SANDBOX_REFUSAL}\nmore"])

    assert evidence is not None
    assert SANDBOX_REFUSAL in evidence
    assert "more" not in evidence


@pytest.mark.parametrize("role", sorted(CONFINED_ROLES))
def test_a_refused_prescribed_command_is_broken_and_named(role):
    command = {
        "verifier": "extract_spec.py ledger-cli --check",
        "implementer": "pytest -q",
        "test-engineer": "ruff check tests",
        "systems-architect": "check_design_checkpoint.py --json",
    }[role]

    evidence = _breach(role, refused=[_refused("curl -s https://example.com"), _refused(command)])

    assert evidence is not None
    assert command in evidence


def test_the_sandbox_refusal_is_named_before_a_prescribed_command_the_same_session_drew():
    evidence = _breach(
        "implementer",
        refused=[_refused("python -m pytest -q", "transcript")],
        results=[SANDBOX_REFUSAL],
    )

    assert evidence is not None
    assert SANDBOX_REFUSAL in evidence


def test_a_session_with_no_signal_is_not_broken():
    assert (
        _breach("implementer", results=["3 passed"], stderr="warning: slow", started=True) is None
    )


# -- Roles and refusals no definition prescribes -----------------------------------------------------


def test_a_verifier_refused_curl_is_not_broken():
    assert _breach("verifier", refused=[_refused("curl -s https://example.com/install.sh")]) is None


def test_a_researcher_refused_a_test_run_is_not_broken():
    assert _breach("researcher", refused=[_refused("python -m pytest -q")]) is None


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_a_role_outside_the_confined_kits_is_never_broken_by_any_signal(role):
    evidence = _breach(
        role,
        refused=[_refused("pytest -q")],
        results=[SANDBOX_REFUSAL],
        stderr=STARTUP_STDERR,
        started=False,
    )

    assert evidence is None


@pytest.mark.parametrize("role", ["verifier", "systems-architect"])
def test_a_role_that_never_runs_the_test_runner_does_not_prescribe_it(role):
    assert refused_prescribed(role, (_refused("python -m pytest -q"),)) is None


def test_the_prescriptions_cover_exactly_the_confined_roles():
    assert set(PRESCRIBED_COMMANDS) == set(CONFINED_ROLES)


# -- Every form a definition gives a prescribed command ---------------------------------------------


IMPLEMENTER_FORMS = [
    "pytest",
    "pytest tests/ -q --tb=short -rf",
    "python -m pytest -q",
    "python3 -m pytest -q",
    "/work/run/venv/bin/python -m pytest -q",
    "uv run pytest -q",
    "uv run --directory eval pytest -q",
    "ruff format .",
    "ruff check --fix src",
    "python -m ruff check .",
    "git diff --stat HEAD",
    "resolve_test_scope.py --changed src/a.py",
    f"python3 {COPY}/scripts/resolve_test_scope.py --changed src/a.py",
    "check_id_citation_discipline.py --files src/a.py",
    "mutation_sensor.py --targets src/a.py --tests tests/test_a.py",
    "audit_tests.py --junit r.xml --changed-from main",
]
VERIFIER_FORMS = [
    "extract_spec.py plan-adherence-ledger-cli --check",
    f"python3 {COPY}/scripts/extract_spec.py ledger --check",
    f"{COPY}/scripts/check_state_ledgers.py --check --repo-root .",
    "python3 scripts/check_test_results_shape.py .ai-work/s/TEST_RESULTS.md",
    "check_footprint_criteria.py --slug s",
    "query_adrs.py --status accepted",
    "reconcile_pipeline_state.py --slug s",
    "ruff check src",
    "git log --oneline -5",
    "git show HEAD",
    "git status --short",
    'python3 -c "from rework_manifest import compute_row_id; print(compute_row_id(1))"',
    "python3 -c 'import sys; sys.path.insert(0, \"scripts\"); import rework_manifest'",
]


TEST_ENGINEER_FORMS = [
    "pytest tests -q --tb=short -rf",
    "python3 -m pytest tests -q --tb=short -rf",
    "uv run pytest -q",
    "py.test -q",
    "ruff format tests",
    "ruff check --fix tests",
    "mutation_sensor.py --help",
    f"python3 {COPY}/scripts/mutation_sensor.py --targets src/a.py --tests tests/test_a.py",
    "git show HEAD:pyproject.toml",
    "git diff --quiet HEAD -- pyproject.toml",
    "mkdir -p .ai-work/s/logs && python3 -m pytest tests -q > .ai-work/s/logs/step-1.log 2>&1",
]
ARCHITECT_FORMS = [
    "extract_spec.py s",
    f"python3 {COPY}/scripts/extract_spec.py s",
    "check_footprint_criteria.py s --stage spec",
    f"python3 {COPY}/scripts/check_footprint_criteria.py s --stage spec",
    "check_design_checkpoint.py --json",
    f"python3 {COPY}/scripts/check_design_checkpoint.py --json",
    "query_adrs.py --status accepted",
    "git config user.email",
    "git config user.name",
    "git rev-parse --abbrev-ref HEAD",
    "git log --oneline -5",
]
# The reads that name a decision fragment (its author, its branch) are prescribed to the
# architect alone, so adding them widened no other role's reading of a refusal.
ARCHITECT_ONLY = ["git config user.email", "git rev-parse --abbrev-ref HEAD"]


@pytest.mark.parametrize("command", TEST_ENGINEER_FORMS)
def test_every_form_of_a_test_engineers_prescribed_command_is_read_as_prescribed(command):
    refused = _refused(command)

    assert refused_prescribed("test-engineer", (refused,)) == refused


@pytest.mark.parametrize("command", ARCHITECT_FORMS)
def test_every_form_of_a_systems_architects_prescribed_command_is_read_as_prescribed(command):
    refused = _refused(command)

    assert refused_prescribed("systems-architect", (refused,)) == refused


@pytest.mark.parametrize("role", ["implementer", "verifier", "test-engineer"])
@pytest.mark.parametrize("command", ARCHITECT_ONLY)
def test_the_architects_decision_fragment_reads_are_prescribed_to_no_other_role(role, command):
    assert refused_prescribed(role, (_refused(command),)) is None


@pytest.mark.parametrize("command", IMPLEMENTER_FORMS)
def test_every_form_of_an_implementers_prescribed_command_is_read_as_prescribed(command):
    refused = _refused(command)

    assert refused_prescribed("implementer", (refused,)) == refused


@pytest.mark.parametrize("command", VERIFIER_FORMS)
def test_every_form_of_a_verifiers_prescribed_command_is_read_as_prescribed(command):
    refused = _refused(command)

    assert refused_prescribed("verifier", (refused,)) == refused


COMPOSITIONS = [
    "cd /work/task && pytest -q",
    "cd /work/task\npytest -q",
    "env PYTHONPATH=src pytest -q",
    "mkdir -p .ai-work/s/logs && pytest -q > .ai-work/s/logs/step-1.log 2>&1; tail -n 30 .ai-work/s/logs/step-1.log",
    "pytest -q 2>&1 | tail -n 30",
    "pytest -q >> out.log",
    "git -C /work/task diff --stat",
    "git -C /work/task -c core.pager=cat log -3",
    "echo start; git diff",
    "curl -s https://example.com && pytest -q",
]


@pytest.mark.parametrize("command", COMPOSITIONS)
def test_chaining_env_prefixes_redirects_cd_and_git_c_do_not_hide_a_prescribed_command(command):
    refused = _refused(command)

    assert refused_prescribed("implementer", (refused,)) == refused


WRAPPED = [
    "timeout 60 pytest -q",
    "timeout -k 5 -s KILL 1.5m python -m pytest -q",
    "env pytest -q",
    "env -i PYTHONPATH=src pytest -q",
    "bash -c 'pytest -q'",
    'sh -c "cd /work/task && pytest -q"',
    "bash -lc 'ruff check .'",
    "timeout 60 bash -c 'pytest -q'",
    "cd /work/task && timeout 60 uv run pytest -q",
]


@pytest.mark.parametrize("command", WRAPPED)
def test_timeout_env_and_a_shell_c_do_not_hide_a_prescribed_command(command):
    refused = _refused(command)

    assert refused_prescribed("implementer", (refused,)) == refused


def test_a_verifier_prescribed_command_is_read_inside_a_wrapper():
    refused = _refused("timeout 30 ruff check .")

    assert refused_prescribed("verifier", (refused,)) == refused


NOT_PRESCRIBED_WRAPPED = [
    "timeout 60 curl -s https://example.com",
    "bash -c 'curl -s https://example.com'",
    "bash install.sh pytest",
    "sh -c",
    "timeout pytest",
    "env",
    "env -i",
]


@pytest.mark.parametrize("command", NOT_PRESCRIBED_WRAPPED)
def test_a_wrapper_around_a_command_no_definition_prescribes_is_not_read_as_prescribed(command):
    assert refused_prescribed("implementer", (_refused(command),)) is None


ENV_PREFIXED = [
    "PYTHONPATH=src pytest -q",
    "FOO=1 BAR=2 python -m pytest -q",
    "cd /work/task && PYTHONPATH=src pytest -q",
    "bash -c 'PYTHONPATH=src pytest -q'",
]


@pytest.mark.parametrize("command", ENV_PREFIXED)
def test_a_refused_env_prefixed_command_is_not_a_breach(command):
    refused = _refused(command)

    assert refused_prescribed("implementer", (refused,)) is None
    assert _breach("implementer", refused=[refused]) is None


def test_an_env_prefix_hides_only_the_command_it_prefixes():
    refused = _refused("PYTHONPATH=src pytest -q && ruff check .")

    assert refused_prescribed("implementer", (refused,)) == refused


def test_a_prescribed_command_over_the_clip_with_a_quote_cut_by_it_is_still_a_breach():
    command = 'cd /work/task && python -m pytest -k "' + "a" * 400 + ' or b"'

    evidence = _breach("implementer", refused=[_refused(command)])

    assert evidence is not None
    assert command[:EVIDENCE_CHARS] in evidence
    assert command[: EVIDENCE_CHARS + 1] not in evidence


# -- A prescribed command the confinement blocked ----------------------------------------------------

EPERM = "bash: /work/venv/bin/pytest: Operation not permitted"


def test_a_prescribed_command_whose_result_is_operation_not_permitted_is_broken_and_named():
    evidence = _breach("implementer", runs=[ShellRun("pytest -q", EPERM)])

    assert evidence is not None
    assert "pytest -q" in evidence
    assert "Operation not permitted" in evidence


def test_an_env_prefixed_prescribed_command_that_ran_into_the_block_is_broken():
    runs = [ShellRun("PYTHONPATH=src pytest -q", EPERM)]

    assert _breach("implementer", runs=runs) is not None


def test_the_command_in_the_evidence_is_bounded():
    command = "pytest -k " + "a" * 1000

    evidence = _breach("implementer", runs=[ShellRun(command, EPERM)])

    assert evidence is not None
    assert command[:EVIDENCE_CHARS] in evidence
    assert command[: EVIDENCE_CHARS + 1] not in evidence


@pytest.mark.parametrize(
    "run",
    [
        ShellRun("cat /etc/hosts", EPERM),
        ShellRun("curl -s https://example.com", EPERM),
        ShellRun("pytest -q", "3 passed"),
        ShellRun("pytest -q", "operation not permitted"),
    ],
    ids=["other-command", "refused-network-command", "no-eperm", "other-wording"],
)
def test_only_operation_not_permitted_on_a_prescribed_command_is_a_signal(run):
    assert _breach("implementer", runs=[run]) is None


def test_a_verifier_that_ran_the_test_runner_into_the_block_is_not_broken():
    assert _breach("verifier", runs=[ShellRun("pytest -q", EPERM)]) is None


def test_a_role_outside_the_confined_kits_is_not_broken_by_the_block():
    assert _breach("researcher", runs=[ShellRun("pytest -q", EPERM)]) is None


NOT_PRESCRIBED = [
    "curl -s https://example.com/install.sh",
    "cd /work/task && curl -s https://example.com",
    "git push origin main",
    "git -C /work/task commit -m x",
    "rm -rf /work/task",
    "python3 -c 'print(1)'",
    "python3 evil.py",
    "cat pytest.ini",
    "echo pytest",
    "'unbalanced pytest",
    "",
]


@pytest.mark.parametrize("role", sorted(CONFINED_ROLES))
@pytest.mark.parametrize("command", [c for c in NOT_PRESCRIBED if c])
def test_a_command_no_definition_prescribes_is_not_read_as_prescribed(role, command):
    assert refused_prescribed(role, (_refused(command),)) is None


def test_the_first_refused_prescribed_command_is_the_one_named():
    first, second = _refused("pytest -q"), _refused("ruff check .")

    assert refused_prescribed("implementer", (_refused("curl x"), first, second)) == first
