"""A confined kit's broken confinement is read from its session's record: the three signals,
the commands a definition prescribes (in every form it gives them), and the roles that never
break a confinement they do not hold."""

from __future__ import annotations

import pytest

from praxion_evals.adherence.confinement import (
    CONFINED_ROLES,
    PRESCRIBED_COMMANDS,
    confinement_breach,
    refused_prescribed,
)
from praxion_evals.adherence.infra_stop import COUNTING_KINDS
from praxion_evals.adherence.model import ERROR_KINDS, Errored, RefusedCommand, Role
from praxion_evals.adherence.session_loop import RETRYABLE_ERRORS

SANDBOX_REFUSAL = "Sandbox is required but failed to initialize: seatbelt denied"
STARTUP_STDERR = "Error: sandbox required by settings (failIfUnavailable) but unavailable."
COPY = "/work/run/plugin"


def _refused(command: str, source="permission_denials") -> RefusedCommand:
    return RefusedCommand(command, source)


def _breach(
    role: Role = "verifier",
    *,
    refused=(),
    results=(),
    stderr="",
    started=True,
) -> str | None:
    return confinement_breach(role, tuple(refused), tuple(results), stderr, started)


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
    command = {"verifier": "extract_spec.py ledger-cli --check", "implementer": "pytest -q"}[role]

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


@pytest.mark.parametrize("role", ["researcher", "test-engineer", "systems-architect"])
def test_a_role_outside_the_confined_kits_is_never_broken_by_any_signal(role):
    evidence = _breach(
        role,
        refused=[_refused("pytest -q")],
        results=[SANDBOX_REFUSAL],
        stderr=STARTUP_STDERR,
        started=False,
    )

    assert evidence is None


def test_the_verifier_does_not_prescribe_the_test_runner():
    assert refused_prescribed("verifier", (_refused("python -m pytest -q"),)) is None


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
    "PYTHONPATH=src pytest -q",
    "FOO=1 BAR=2 python -m pytest -q",
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


@pytest.mark.parametrize("command", [c for c in NOT_PRESCRIBED if c])
def test_a_command_no_definition_prescribes_is_not_read_as_prescribed(command):
    assert refused_prescribed("implementer", (_refused(command),)) is None
    assert refused_prescribed("verifier", (_refused(command),)) is None


def test_the_first_refused_prescribed_command_is_the_one_named():
    first, second = _refused("pytest -q"), _refused("ruff check .")

    assert refused_prescribed("implementer", (_refused("curl x"), first, second)) == first
