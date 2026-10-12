"""Every graded session ends in one outcome per check, and errors never count against a role.

A session that failed for infrastructure reasons (a crash, a timeout, an isolation
breach shown by its own startup telemetry) is recorded errored with its kind and
grades nothing. A session whose main session never spawned the role is not
measured. A spawned role that produced nothing fails the checks that needed an
observation. Each session carries its setup and the spawned role's first-request
tokens, read from its own stream.
"""

from __future__ import annotations

from tests.acceptance.drivers.adherence_eval import (
    ROLE_FIRST_REQUEST_TOKENS,
    SessionEvidence,
    SessionSetup,
    grade,
    scratch_repo,
    session_envelope,
    session_places,
)

CHECKS = ["C1", "C2", "C4"]


def _graded_counts(graded) -> list[str]:
    return [name for name, o in graded.outcomes.items() if o.kind in {"passed", "failed"}]


def test_a_session_that_crashed_before_writing_its_stream_is_errored_and_grades_nothing(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)

    graded = grade(SessionEvidence("researcher", repo, "", places, exit_code=1), CHECKS)

    assert graded.errored_kind, "a crashed session is recorded errored with its kind"
    assert _graded_counts(graded) == [], "an errored session entered a pass rate"


def test_a_session_that_timed_out_is_errored_and_grades_nothing(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    started_only = session_envelope(
        role="researcher", cwd=repo.root, plugin_copy=places.plugin_copy
    ).splitlines()[0]

    evidence = SessionEvidence(
        "researcher", repo, started_only + "\n", places, exit_code=None, timed_out=True
    )
    graded = grade(evidence, CHECKS)

    assert graded.errored_kind, "a timed-out session is recorded errored with its kind"
    assert _graded_counts(graded) == []


def test_a_session_whose_telemetry_shows_a_plugin_from_outside_the_sandbox_is_an_isolation_error(
    tmp_path,
):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    envelope = session_envelope(
        role="researcher",
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        return_text="Done.\n[COMPLETE]",
        extra_plugins=[
            {
                "name": "praxion",
                "path": "/Users/operator/.claude/plugins/marketplaces/praxion-marketplace/praxion",
                "source": "praxion@praxion-marketplace",
            }
        ],
    )

    graded = grade(SessionEvidence("researcher", repo, envelope, places), CHECKS)

    assert "isolation" in (graded.errored_kind or ""), f"errored kind: {graded.errored_kind!r}"
    assert _graded_counts(graded) == []


def test_a_session_whose_main_session_never_spawned_the_role_is_not_measured(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    envelope = session_envelope(
        role="researcher",
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        spawned=False,
        relay_text="I looked it up myself.\n[COMPLETE]",
    )

    graded = grade(SessionEvidence("researcher", repo, envelope, places), CHECKS)

    assert graded.not_measured
    assert graded.errored_kind is None
    assert _graded_counts(graded) == [], "a session that never spawned the role entered a pass rate"


def test_a_spawned_role_that_produced_nothing_fails_rather_than_passing_vacuously(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    envelope = session_envelope(
        role="researcher", cwd=repo.root, plugin_copy=places.plugin_copy, return_text=None
    )

    graded = grade(SessionEvidence("researcher", repo, envelope, places), ["C1", "C2"])

    assert (graded.outcome("C1").kind, graded.outcome("C2").kind) == ("failed", "failed")


def test_a_graded_session_carries_its_setup_and_the_spawned_roles_first_request_tokens(tmp_path):
    repo = scratch_repo(tmp_path)
    places = session_places(tmp_path)
    findings = repo.put(
        ".ai-work/adherence-task/RESEARCH_FINDINGS.md", "# Research Findings: keys\n"
    )
    envelope = session_envelope(
        role="researcher",
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        actions=[],
        return_text=f"Findings: {findings.name}\n[COMPLETE]",
    )
    setup = SessionSetup(
        arm="lean",
        checkout_commit="0123456789abcdef0123456789abcdef01234567",
        role="researcher",
        task_id="researcher-api-docs-03",
        seed=7,
    )

    graded = grade(SessionEvidence("researcher", repo, envelope, places, setup=setup), ["C1"])

    assert graded.first_request_tokens == ROLE_FIRST_REQUEST_TOKENS, (
        "the first-request figure is not the spawned role's own (the main session's is 49374)"
    )
    assert {
        k: graded.setup.get(k) for k in ("arm", "checkout_commit", "role", "task_id", "seed")
    } == {
        "arm": "lean",
        "checkout_commit": "0123456789abcdef0123456789abcdef01234567",
        "role": "researcher",
        "task_id": "researcher-api-docs-03",
        "seed": 7,
    }
