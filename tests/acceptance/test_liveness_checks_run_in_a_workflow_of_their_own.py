"""The liveness checks run in a workflow of their own, each kind of check in a job of its own.

The gate-liveness command and the liveness-marked scenarios run from one workflow that is not the
scheduled test-health workflow, under a name no other workflow carries. Its three fast probes run
in a job that neither runs nor waits for the selection audit; the audit runs in a job of its own
whose red is the run's red and hides no other job's conclusion; the whole-suite scenarios run
apart from the quick ones. Every job keeps the safety properties the old jobs held, and its time
limit carries the reading it was sized from. The scheduled test-health workflow keeps only its
health jobs, and a red liveness run starts no autofix session.
"""

from __future__ import annotations

import re
import tomllib

import pytest
import yaml

from tests.acceptance.drivers.liveness_workflow import (
    _SESSION_COMMAND,
    _SHA_PIN,
    AUDIT_PROBE,
    AUTOFIX,
    AUTOFIX_WATCHED,
    FAST_JOB_MAXIMUM_MINUTES,
    GATE_COMMAND,
    MARKER,
    QUICK_PROBES,
    QUICK_SCENARIO_FILES,
    REACHING_TOKENS,
    REPO_ROOT,
    RUNNER_JOB_MAXIMUM_MINUTES,
    SCENARIO_TREES,
    SCHEDULED,
    SCHEDULED_NAME,
    SESSION_TOKENS,
    SYNC_STEP,
    SYNCED_PYTHON,
    WHOLE_SUITE_SCENARIO_FILES,
    all_workflows,
    audit_job,
    collected_by_job,
    fast_probe_job,
    gate_invocations,
    gate_runs_outside_the_synced_environment,
    header_comment,
    job_level_limit,
    jobs_collecting,
    limit_annotation,
    liveness_marked_scenarios,
    liveness_workflow,
    load,
    needs_closure,
    path_arguments,
    probes_selected,
    pytest_invocations,
    run_texts,
    runs_a_liveness_check,
    scenario_jobs,
    selects_the_marker,
)

STEP_LOOP_BOUND_SECONDS = 2500


# -- A workflow of its own --------------------------------------------------------------------


def test_a_workflow_other_than_the_scheduled_one_runs_the_command_and_the_scenarios():
    workflow = liveness_workflow()

    jobs = workflow.jobs.values()

    assert any(gate_invocations(job) for job in jobs), f"{workflow.relpath} runs no {GATE_COMMAND}"
    assert scenario_jobs(workflow), f"{workflow.relpath} runs no {MARKER}-marked scenarios"


def test_the_liveness_workflow_has_a_name_no_other_workflow_carries():
    workflow = liveness_workflow()

    others = {wf.name for wf in all_workflows() if wf.relpath != workflow.relpath}

    assert workflow.name, f"{workflow.relpath} has no name"
    assert workflow.name != SCHEDULED_NAME, f"{workflow.relpath} is named {SCHEDULED_NAME!r}"
    assert workflow.name not in others, f"another workflow is also named {workflow.name!r}"


def test_the_scheduled_test_health_workflow_runs_no_liveness_check():
    scheduled = load(SCHEDULED)

    hosting = [job_id for job_id, job in scheduled.jobs.items() if runs_a_liveness_check(job)]

    assert hosting == [], f"{SCHEDULED} still runs a liveness check in {hosting}"


# -- The fast probes and the selection audit, each in a job of its own -----------------------


def test_the_fast_probe_job_runs_exactly_the_three_fast_probes_and_never_the_audit():
    workflow = liveness_workflow()
    fast = fast_probe_job(workflow)

    selections = [probes_selected(argv) for argv in gate_invocations(workflow.jobs[fast])]

    assert all(set(chosen) == set(QUICK_PROBES) for chosen in selections), (
        f"the fast-probe job {fast} runs {selections}, not only {QUICK_PROBES}"
    )


def test_the_fast_probe_job_neither_waits_for_nor_depends_on_the_audit_job():
    workflow = liveness_workflow()
    fast, audit = fast_probe_job(workflow), audit_job(workflow)

    condition = str(workflow.jobs[fast].get("if", ""))

    assert fast != audit, "the fast probes and the selection audit share one job"
    assert audit not in needs_closure(workflow, fast), f"{fast} waits for the audit job {audit}"
    assert audit not in condition, f"the fast-probe job's condition names the audit: {condition!r}"
    assert "needs." not in condition, f"the fast-probe job's condition reads a job: {condition!r}"


def test_the_audit_job_runs_only_the_selection_audit():
    workflow = liveness_workflow()
    audit = audit_job(workflow)

    selections = [probes_selected(argv) for argv in gate_invocations(workflow.jobs[audit])]

    assert selections, f"the audit job {audit} runs no gate-liveness command"
    assert all(chosen == (AUDIT_PROBE,) for chosen in selections), (
        f"the audit job {audit} runs {selections}, not the selection audit alone"
    )


def test_a_failing_audit_fails_its_job_and_the_run():
    workflow = liveness_workflow()
    audit = audit_job(workflow)
    job = workflow.jobs[audit]

    tolerant = [
        step.get("name") or step.get("run")
        for step in job.get("steps", [])
        if step.get("continue-on-error") and GATE_COMMAND in str(step.get("run", ""))
    ]

    assert not job.get("continue-on-error"), f"the audit job {audit} continues on error"
    assert tolerant == [], f"the audit step continues on error: {tolerant}"


def test_every_other_job_still_shows_its_own_conclusion_when_the_audit_fails():
    workflow = liveness_workflow()
    audit = audit_job(workflow)

    held_back = [
        job_id
        for job_id, job in workflow.jobs.items()
        if job_id != audit
        and audit in needs_closure(workflow, job_id)
        and "always()" not in str(job.get("if", ""))
    ]

    assert held_back == [], f"these jobs are skipped whenever the audit fails: {held_back}"


# -- The invariants every liveness job keeps -------------------------------------------------


def test_every_liveness_job_holds_a_read_only_contents_grant_and_nothing_else():
    workflow = liveness_workflow()

    grants = {job_id: workflow.permissions_of(job_id) for job_id in workflow.jobs}

    assert all(grant == {"contents": "read"} for grant in grants.values()), (
        f"each job's grant must be exactly a read of contents: {grants}"
    )


def test_no_liveness_job_reaches_a_secret_or_starts_an_assistant_session():
    workflow = liveness_workflow()

    parsed = yaml.safe_dump({k: v for k, v in workflow.data.items() if k not in ("name",)})
    sessions = [
        text
        for job in workflow.jobs.values()
        for text in run_texts(job)
        if _SESSION_COMMAND.search(text)
    ]

    reached = [token for token in (*REACHING_TOKENS, *SESSION_TOKENS) if token in parsed]
    assert reached == [], f"{workflow.relpath} reaches {reached}"
    assert sessions == [], f"{workflow.relpath} starts an assistant session: {sessions}"


def test_the_gate_command_runs_only_from_the_synced_environment_after_it_is_built():
    workflow = liveness_workflow()

    misrun = gate_runs_outside_the_synced_environment(workflow)

    assert misrun == {}, (
        f"run the command only as `{SYNCED_PYTHON} {GATE_COMMAND}` after `{SYNC_STEP}`: {misrun}"
    )


def test_every_pytest_run_selects_the_liveness_marker_over_the_scenario_trees_only():
    workflow = liveness_workflow()

    invocations = [argv for job in workflow.jobs.values() for argv in pytest_invocations(job)]
    unmarked = [argv for argv in invocations if not selects_the_marker(argv)]
    outside = [
        argv
        for argv in invocations
        if not path_arguments(argv)
        or any(not p.rstrip("/").startswith(SCENARIO_TREES) for p in path_arguments(argv))
    ]

    assert invocations, f"{workflow.relpath} runs no pytest"
    assert unmarked == [], f"pytest runs without the {MARKER} marker: {unmarked}"
    assert outside == [], f"pytest runs reach beyond {SCENARIO_TREES}: {outside}"


def test_the_liveness_jobs_together_run_every_liveness_marked_scenario_and_no_other():
    workflow = liveness_workflow()

    collected = frozenset().union(*(collected_by_job(workflow, j) for j in workflow.jobs))
    expected = liveness_marked_scenarios()

    assert collected == expected, (
        f"missing: {sorted(expected - collected)}\nextra: {sorted(collected - expected)}"
    )


def test_no_pytest_run_collects_the_root_tree_and_the_fitness_tree_together():
    workflow = liveness_workflow()

    mixed = [
        argv
        for job in workflow.jobs.values()
        for argv in pytest_invocations(job)
        if any("fitness" in arg for arg in argv)
    ]

    assert mixed == [], f"a pytest run reaches the fitness tree: {mixed}"


def test_every_action_the_liveness_workflow_uses_is_pinned_to_a_full_commit_hash():
    workflow = liveness_workflow()

    unpinned = [
        step["uses"]
        for job in workflow.jobs.values()
        for step in job.get("steps", [])
        if step.get("uses") and not _SHA_PIN.search(step["uses"])
    ]

    assert unpinned == [], f"unpinned actions: {unpinned}"


# -- Each time limit, beside the reading it was sized from -----------------------------------

READING_PARTS = {
    "a duration": r"\b\d+(?:\.\d+)?\s?(?:s|sec|seconds|min|minutes)\b",
    "the commit it was taken on": r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b",
    "local or on the runner": r"\b(?:local(?:ly)?|runner)\b",
    "the scaling used": r"\bscal(?:ed|ing|e)\b|\bunscaled\b",
    "the margin of one and a half": r"\b1\.5\s?(?:x|×|times)?|\bone and a half\b",
    "when it was measured": r"\b\d{4}-\d{2}-\d{2}\b",
}


@pytest.mark.parametrize("part", sorted(READING_PARTS))
def test_each_job_limit_states_beside_it_the_reading_it_was_sized_from(part):
    workflow = liveness_workflow()

    unstated = [
        job_id
        for job_id in workflow.jobs
        if not re.search(READING_PARTS[part], limit_annotation(workflow, job_id), re.IGNORECASE)
    ]

    assert unstated == [], f"the limit of {unstated} does not state {part} beside it"


def test_no_job_limit_passes_the_runner_maximum_and_the_fast_job_stays_within_twenty_minutes():
    workflow = liveness_workflow()

    limits = {job_id: job_level_limit(workflow, job_id) for job_id in workflow.jobs}
    fast = fast_probe_job(workflow)

    assert all(0 < (limit or 0) <= RUNNER_JOB_MAXIMUM_MINUTES for limit in limits.values()), limits
    assert (limits[fast] or 0) <= FAST_JOB_MAXIMUM_MINUTES, limits


# -- The whole-suite scenarios apart from the quick ones -------------------------------------


def test_the_whole_suite_scenarios_run_in_a_job_apart_from_the_quick_scenarios():
    workflow = liveness_workflow()

    whole_suite = jobs_collecting(workflow, WHOLE_SUITE_SCENARIO_FILES)
    quick = jobs_collecting(workflow, QUICK_SCENARIO_FILES)

    assert whole_suite, "no liveness job runs the whole-suite scenarios"
    assert quick, "no liveness job runs the quick scenarios"
    assert not whole_suite & quick, f"one job runs both kinds of scenario: {whole_suite & quick}"


def test_the_quick_scenarios_job_concludes_whatever_the_whole_suite_scenarios_do():
    workflow = liveness_workflow()

    whole_suite = jobs_collecting(workflow, WHOLE_SUITE_SCENARIO_FILES)
    waiting = {
        job_id: needs_closure(workflow, job_id) & whole_suite
        for job_id in jobs_collecting(workflow, QUICK_SCENARIO_FILES)
    }

    assert not any(waiting.values()), f"quick-scenario jobs wait for whole-suite ones: {waiting}"


def test_the_step_loop_still_holds_the_root_pocket_to_its_declared_bound():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    bound = project["tool"]["praxion"]["step-loop"]["gate-timeout-seconds"]

    assert bound == STEP_LOOP_BOUND_SECONDS


# -- The scheduled health run and the autofix watch list -------------------------------------


def test_the_scheduled_workflow_header_describes_only_the_jobs_it_runs():
    header = header_comment(SCHEDULED)

    named = [term for term in (GATE_COMMAND, "gate-liveness", "liveness-marked") if term in header]

    assert named == [], f"the header of {SCHEDULED} still describes the liveness checks: {named}"


def test_the_autofix_workflow_still_watches_exactly_its_three_workflows():
    autofix = load(AUTOFIX)

    watched = autofix.triggers["workflow_run"]["workflows"]

    assert watched == AUTOFIX_WATCHED


def test_no_workflow_starts_a_run_when_the_liveness_workflow_finishes():
    workflow = liveness_workflow()

    watchers = [
        wf.relpath
        for wf in all_workflows()
        if workflow.name in ((wf.triggers.get("workflow_run") or {}).get("workflows") or [])
    ]

    assert watchers == [], f"these workflows run when {workflow.name!r} finishes: {watchers}"
