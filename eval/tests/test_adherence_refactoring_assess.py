"""Assessing a pool session: the default checks, then the role's end-state items and the arrival.

The end state is graded over each template's committed ``end_states`` trees; the arrival is read
from recorded role transcripts of the proof tests. No session is started.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence import (
    axis_runs,
    checks_refactoring,
    refactoring_arms,
    refactoring_assess,
    refactoring_tasks,
    tasks,
)
from praxion_evals.adherence.arms import DeliveryObservation
from praxion_evals.adherence.checks_roles import CHECKOUT_ROOT, section_body
from praxion_evals.adherence.model import (
    CheckErrored,
    EarlyStop,
    Errored,
    Failed,
    Measured,
    NotApplicable,
    NotMeasured,
    Passed,
    SessionSetup,
    Standard,
)
from praxion_evals.live.session import SandboxPaths
from tests.test_adherence_refactoring_proof import _RENDER, REPO_ROOT, _evidence, _preload, _user
from tests.test_refactoring_grades_implementer import _slug
from tests.test_refactoring_grades_implementer import _workspace as _build_workspace

SEED = 7
ACCOUNT = "Done: every checklist item holds."
CONFESSES = "I left a compatibility shim and some dead code."
HOME = Path("/nonexistent-home")
ARRIVES = DeliveryObservation(1, 0, 0, 450)
DEFAULT_OUTCOMES = {"C1": Passed(), "C2": Failed("did not ask")}
KERNEL_ROWS = ({"kernel_version": "v1", "slot": 1},)

CASES = [
    (role, template)
    for role in ("implementer", "test-engineer")
    for template in refactoring_tasks.POOLS[role].fixture_of
]


@pytest.fixture(scope="module")
def block() -> str:
    done = subprocess.run(
        [sys.executable, "-B", "-c", _RENDER, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def _task(role, template_id, variant=None):
    task = next(t for t in refactoring_tasks.pool_tasks(role, SEED) if t.template_id == template_id)
    return task if variant is None else replace(task, variant=variant)


def _setup(task, arm="delivered"):
    return SessionSetup(arm, "abc1234", task.role, task.task_id, task.template_id, SEED,
                        axis="refactoring-delivery")  # fmt: skip


def _default():
    return Measured.for_checks(
        list(DEFAULT_OUTCOMES), DEFAULT_OUTCOMES, 450, role_return="the return",
        kernel_rows=KERNEL_ROWS,
    )  # fmt: skip


def _session(tmp_path, task, end_state="clean", *, records=None, account=ACCOUNT):
    """Evidence of ``task`` whose scratch repository holds ``end_state`` over the template's start."""
    evidence = replace(_evidence(tmp_path, records), role=task.role, role_return=account)
    template = tasks.FIXTURES_DIR / task.role / refactoring_tasks.POOL_DIRNAME / task.template_id
    workspace = _build_workspace(tmp_path / "built", end_state, template)
    shutil.copytree(workspace, tasks.scratch_dir(SandboxPaths(evidence.sandbox)))
    return evidence


def _extend(evidence, task, arm="delivered", real_home=HOME):
    return refactoring_assess.extend(_default(), evidence, task, _setup(task, arm), real_home)


@pytest.fixture
def arrives(monkeypatch):
    monkeypatch.setattr(refactoring_arms, "observe_delivery", lambda evidence, home: ARRIVES)


def _item_outcomes(status, role):
    return {name: status.outcomes[name] for name in refactoring_assess.item_names(role)}


# --- the end state ----------------------------------------------------------------------------


@pytest.mark.parametrize(("role", "template"), CASES)
def test_a_clean_end_state_passes_every_item_whatever_the_account_says(
    tmp_path, arrives, role, template
):
    task = _task(role, template)

    status = _extend(_session(tmp_path, task, account=CONFESSES), task)

    assert set(_item_outcomes(status, role).values()) == {Passed()}


@pytest.mark.parametrize(
    ("role", "template", "item"),
    [
        (role, template, item)
        for role, template in CASES
        for item, _ in checks_refactoring.CHECKLISTS[role]
    ],
)
def test_a_violating_end_state_fails_exactly_its_item(tmp_path, arrives, role, template, item):
    task = _task(role, template)

    status = _extend(_session(tmp_path, task, _slug(item)), task)

    failed = {n for n, o in _item_outcomes(status, role).items() if isinstance(o, Failed)}
    assert failed == {refactoring_assess.item_name(item)}


def test_a_forced_stop_session_reads_not_applicable_on_the_items_and_is_still_read_for_arrival(
    tmp_path, arrives
):
    task = _task("implementer", "refactoring-extract-module", EarlyStop(turn_cap=3))

    status = _extend(_session(tmp_path, task, "no-dead-code-remains"), task)

    items = _item_outcomes(status, "implementer").values()
    assert set(items) == {NotApplicable(refactoring_assess.STOPPED_EARLY)}
    assert status.outcomes[refactoring_assess.ARRIVAL] == Passed()


def test_a_grader_that_raises_reads_check_errored_on_every_item(tmp_path, arrives, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("refactoring.toml lacks a string for target")

    monkeypatch.setattr(checks_refactoring, "grade_workspace", boom)
    task = _task("test-engineer", "refactoring-characterize")

    status = _extend(_session(tmp_path, task), task)

    for outcome in _item_outcomes(status, "test-engineer").values():
        assert isinstance(outcome, CheckErrored)
        assert "ValueError" in outcome.reason
        assert "lacks a string for target" in outcome.reason


def test_the_grader_is_handed_the_template_manifest_and_the_scratch_repository(
    tmp_path, arrives, monkeypatch
):
    seen = {}

    def spy(role, workspace, account, *, manifest=None):
        seen.update(role=role, workspace=workspace, account=account, manifest=manifest)
        return checks_refactoring.RefactoringGrade(())

    monkeypatch.setattr(checks_refactoring, "grade_workspace", spy)
    task = _task("implementer", "refactoring-extract-module-notes-service")
    evidence = _session(tmp_path, task)

    _extend(evidence, task)

    assert seen["workspace"] == tasks.scratch_dir(SandboxPaths(evidence.sandbox))
    assert seen["manifest"] == refactoring_tasks.manifest_path(task)
    assert seen["manifest"].is_file()
    assert (seen["role"], seen["account"]) == ("implementer", ACCOUNT)


# --- the arrival ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arm", "records_of"),
    [
        ("delivered", lambda block: [_user("go\n\n" + block)]),
        ("preloaded", lambda block: [_preload()]),
    ],
)
def test_the_arrival_passes_when_the_skill_reached_the_role_its_arms_way(
    tmp_path, block, monkeypatch, arm, records_of
):
    task = _task("implementer", "refactoring-extract-module")
    monkeypatch.setattr(refactoring_assess, "_end_state", lambda evidence, task: {})
    evidence = _evidence(tmp_path, records_of(block))

    status = _extend(evidence, task, arm)

    assert status.outcomes[refactoring_assess.ARRIVAL] == Passed()


@pytest.mark.parametrize(
    ("arm", "records_of", "held"),
    [
        ("delivered", lambda block: [_preload()], "(0, 0, 1)"),
        ("delivered", lambda block: [_user(block), _preload()], "(1, 0, 1)"),
        ("preloaded", lambda block: [_user(block)], "(1, 0, 0)"),
        ("preloaded", lambda block: [_user("no skill here")], "(0, 0, 0)"),
    ],
)
def test_the_arrival_fails_when_the_skill_reached_the_role_the_other_arms_way(
    tmp_path, block, monkeypatch, arm, records_of, held
):
    task = _task("implementer", "refactoring-extract-module")
    monkeypatch.setattr(refactoring_assess, "_end_state", lambda evidence, task: {})
    evidence = _evidence(tmp_path, records_of(block))

    outcome = _extend(evidence, task, arm).outcomes[refactoring_assess.ARRIVAL]

    assert isinstance(outcome, Failed)
    assert held in outcome.detail


def test_the_arrival_reads_check_errored_when_the_transcript_cannot_be_read(tmp_path, monkeypatch):
    task = _task("implementer", "refactoring-extract-module")
    monkeypatch.setattr(refactoring_assess, "_end_state", lambda evidence, task: {})

    outcome = _extend(_evidence(tmp_path, None), task).outcomes[refactoring_assess.ARRIVAL]

    assert isinstance(outcome, CheckErrored)
    assert "cannot be read" in outcome.reason


def test_the_arrival_reads_check_errored_when_no_real_home_was_given(tmp_path, monkeypatch):
    task = _task("implementer", "refactoring-extract-module")
    monkeypatch.setattr(refactoring_assess, "_end_state", lambda evidence, task: {})

    status = _extend(_evidence(tmp_path, None), task, real_home=None)

    assert isinstance(status.outcomes[refactoring_assess.ARRIVAL], CheckErrored)


# --- the result -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "default",
    [Errored("timeout", "exit_code=None"), NotMeasured("the main session never spawned it")],
)
def test_a_result_that_was_not_measured_is_returned_unchanged(default):
    task = _task("implementer", "refactoring-extract-module")

    extended = refactoring_assess.extend(default, None, task, _setup(task), HOME)  # type: ignore[arg-type]

    assert extended is default


@pytest.mark.parametrize("role", ["implementer", "test-engineer"])
def test_the_result_holds_exactly_the_default_names_and_the_axis_names(tmp_path, arrives, role):
    template = next(t for r, t in CASES if r == role)
    task = _task(role, template)

    status = _extend(_session(tmp_path, task), task)

    assert list(status.outcomes) == [
        *DEFAULT_OUTCOMES,
        *refactoring_assess.item_names(role),
        refactoring_assess.ARRIVAL,
    ]
    assert {n: status.outcomes[n] for n in DEFAULT_OUTCOMES} == DEFAULT_OUTCOMES


def test_the_result_carries_the_default_results_tokens_setup_return_kernel_rows_and_ending(
    tmp_path, arrives
):
    task = _task("implementer", "refactoring-extract-module")

    status = _extend(_session(tmp_path, task), task)

    default = _default()
    assert (status.first_request_tokens, status.setup, status.role_return) == (
        default.first_request_tokens,
        default.setup,
        default.role_return,
    )
    assert (status.kernel_rows, status.role_ending) == (KERNEL_ROWS, default.role_ending)


def test_the_axis_assessment_runs_the_default_assessment_first(tmp_path, arrives, monkeypatch):
    task = _task("implementer", "refactoring-extract-module", Standard())
    monkeypatch.setattr(axis_runs.grade, "grade", lambda *args, **kwargs: _default())

    status = axis_runs.axis_run("refactoring-delivery").assess(
        _session(tmp_path, task), task, _setup(task), None, HOME
    )

    assert list(status.outcomes)[:2] == list(DEFAULT_OUTCOMES)
    assert refactoring_assess.ARRIVAL in status.outcomes


# --- the catalog ------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["implementer", "test-engineer"])
def test_the_catalog_entries_carry_the_names_of_the_outcomes(role):
    entries = refactoring_assess.catalog_entries(role)

    assert [e.name for e in entries] == [
        *refactoring_assess.item_names(role),
        refactoring_assess.ARRIVAL,
    ]
    assert {(e.kind, e.common, e.golden_bad_case) for e in entries} == {("mechanical", False, None)}


@pytest.mark.parametrize("role", ["implementer", "test-engineer"])
def test_each_entry_cites_a_heading_that_is_in_the_skill(role):
    text = (CHECKOUT_ROOT / refactoring_assess.SKILL).read_text()

    for entry in refactoring_assess.catalog_entries(role):
        assert entry.rule.file == refactoring_assess.SKILL
        assert section_body(text, entry.rule.section) is not None, entry.rule.section


def test_the_items_cite_the_checklist_for_the_implementer_and_the_gotchas_for_the_test_engineer():
    sections = {
        role: {e.rule.section for e in refactoring_assess.catalog_entries(role)[:-1]}
        for role in ("implementer", "test-engineer")
    }

    assert sections == {"implementer": {"Verification Checklist"}, "test-engineer": {"Gotchas"}}
    assert refactoring_assess.catalog_entries("implementer")[-1].rule.section == "Entry Points"


@pytest.mark.parametrize("role", ["implementer", "test-engineer"])
def test_the_axis_catalog_lists_the_default_entries_first_and_the_default_axis_is_untouched(role):
    default = axis_runs.DEFAULT_RUN
    other = axis_runs.axis_run("refactoring-delivery")

    assert other.catalog(role) == (
        *default.catalog(role),
        *refactoring_assess.catalog_entries(role),
    )
    assert default.catalog is axis_runs.catalog_entries
    assert default.assess is axis_runs.assess_session


def test_a_pool_tasks_manifest_is_the_templates_and_is_not_staged(tmp_path):
    task = _task("implementer", "refactoring-extract-module")
    staged = tmp_path / "repo"

    refactoring_tasks.stage_pool_task(task, staged)

    assert refactoring_tasks.manifest_path(task).read_text()
    assert not list(staged.rglob(checks_refactoring.MANIFEST))
