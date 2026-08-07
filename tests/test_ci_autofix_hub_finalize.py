"""Structural invariants for the ci-autofix hub's finalize/decline step.

Covers the green-decline mechanism that normalizes every non-fix terminal
state: the fixer step's `continue-on-error`, and the non-agent finalize step
that converts a crash, a turn-budget exhaustion, or a deliberate no-fix into
one countable `autofix:declined` outcome — idempotently, fail-closed, and
scoped to the surfaces that actually attempt a fix.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps and gates. It cannot verify runtime behavior (what
actually happens on a live run); where a test is a structural proxy for a
runtime guarantee, its docstring says so explicitly, and the guarantee closes
via dogfooding once Praxion's own caller exercises the hub in production CI.

Every test reads the workflow lazily (inside the function body, never at module
import time) so collection succeeds even when the file is absent — an absent
hub then fails with a clear assertion, never an import error.

Sibling modules covering the same workflow file:
`test_ci_autofix_hub_contract.py` (file-wide interface/security contract),
`test_ci_autofix_hub_surfaces.py` (classify / same-repo-pr / fork jobs),
`test_ci_autofix_hub_finalize.py` (green-decline finalize step),
`test_ci_autofix_hub_js_runner.py` (policy-gated JS/TS runner grant),
`test_ci_autofix_hub_pm_install.py` (package-manager detection + install step).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HUB_WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "reusable-ci-autofix.yml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_text() -> str:
    """Return the hub workflow's raw file content (read lazily so collection succeeds)."""
    return HUB_WORKFLOW_FILE.read_text(encoding="utf-8")


def _parsed() -> dict:
    """Parse the hub workflow as YAML."""
    return yaml.safe_load(_raw_text())


def _job(parsed: dict, name: str) -> dict:
    """Return a named job's body, or `{}` if the job doesn't exist yet (RED-safe)."""
    return (parsed.get("jobs") or {}).get(name) or {}


def _agent_steps(job: dict) -> list[dict]:
    """Return every `claude-code-action` step within a single job."""
    return [
        step for step in job.get("steps") or [] if "claude-code-action" in (step.get("uses") or "")
    ]


def _finalize_step(job: dict) -> dict | None:
    """Return the non-agent finalize/decline step in a job, or `None` if it
    does not exist yet (RED-safe)."""
    for step in job.get("steps") or []:
        if "finalize" in (step.get("name") or "").lower():
            return step
    return None


# ---------------------------------------------------------------------------
# Bug A — finalize/decline step (normalize every non-fix terminal state)
#
# RED-phase note: every assertion below expects the shipped file, at time of
# writing, to lack `continue-on-error` on the fixer step and to lack a
# finalize/decline step entirely — expected failures are "attribute absent" /
# "step not found" shapes, never a collection or import error. The two
# exceptions are explicitly called out in their own docstrings as GREEN by
# construction (a preventive regression guard, not a TDD-red assertion):
# `test_allowedtools_value_stays_a_single_physical_line_in_every_agent_step`
# and `test_finalize_step_is_scoped_to_autofix_same_repo_pr_only` (the latter
# is a negative/absence proxy for the "main and fork jobs stay byte-unchanged"
# guarantee, not explicitly named in the plan's RED list, but structurally
# identical in kind to the single-line invariant: it cannot go RED before the
# finalize step exists anywhere to misplace).
# ---------------------------------------------------------------------------


def test_fixer_step_has_continue_on_error_so_a_crash_does_not_fail_the_job() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    fixer_step = agent_steps[0]
    assert fixer_step.get("continue-on-error") is True, (
        "The fixer step must carry `continue-on-error: true` so an agent crash "
        "(e.g. turn-budget exhaustion) does not fail the job — the finalize "
        "step converts every non-fix outcome into a clean decline instead"
    )


def test_finalize_step_exists_as_a_non_agent_step_after_the_push_step() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    step_names = [step.get("name", "") for step in job.get("steps") or []]
    finalize_step = _finalize_step(job)
    assert finalize_step is not None, (
        "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    )
    assert "uses" not in finalize_step, "The finalize step must be a non-agent `run:` step"
    push_index = next(i for i, name in enumerate(step_names) if "push" in name.lower())
    tripwire_index = next(i for i, name in enumerate(step_names) if "sensitive" in name.lower())
    finalize_index = step_names.index(finalize_step.get("name", ""))
    assert push_index < finalize_index < tripwire_index, (
        "The finalize step must run after the push step and before the sensitive-path tripwire step"
    )


def test_finalize_step_is_guarded_on_always_and_budget_proceed() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert finalize_step is not None, (
        "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    )
    condition = finalize_step.get("if") or ""
    assert "always()" in condition, (
        "The finalize step's `if:` must include `always()` so it still runs "
        "on the fixer-crash path, where `continue-on-error` leaves the "
        "step's own default `success()` condition unmet"
    )
    assert "steps.budget.outputs.proceed" in condition, (
        "The finalize step's `if:` must gate on `steps.budget.outputs.proceed` "
        "so it is skipped when an earlier gate already declined the run"
    )


def test_finalize_step_declines_when_no_fix_commit_and_no_existing_label() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert finalize_step is not None, (
        "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    )
    run = finalize_step.get("run") or ""
    assert "PRE_AGENT_HEAD" in run, (
        "The finalize step must compare current HEAD against a "
        "PRE_AGENT_HEAD-shaped value to detect whether a fix commit exists"
    )
    assert re.search(r"gh pr view.*--json labels", run), (
        "The finalize step must read the PR's labels via `gh pr view ... "
        "--json labels` to check for an existing autofix:declined label"
    )
    assert "gh pr comment" in run, (
        "The no-fix/no-label branch must post a bounded root-cause comment via `gh pr comment`"
    )
    assert re.search(r"gh pr edit.*--add-label.*autofix:declined", run), (
        "The no-fix/no-label branch must apply the `autofix:declined` label "
        "via `gh pr edit --add-label`"
    )
    assert re.search(r"^exit 0$", run, re.MULTILINE), (
        "The finalize step must end with a bare, top-level `exit 0` so the "
        "job always reports success on this path"
    )


def test_finalize_step_is_idempotent_noop_when_declined_label_already_present() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert finalize_step is not None, (
        "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    )
    run = finalize_step.get("run") or ""
    assert run.count("gh pr comment") == 1, (
        "The finalize step must call `gh pr comment` exactly once — the "
        "already-declined branch must short-circuit before reaching it, "
        "never posting a duplicate comment"
    )
    assert "autofix:declined" in run, "The finalize step must reference the autofix:declined label"
    assert run.count("--add-label") == 1, (
        "The finalize step must apply the `autofix:declined` label exactly "
        "once — the already-declined branch must short-circuit before "
        "reaching a second label write"
    )


def test_finalize_step_noops_when_a_fix_commit_was_produced() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert finalize_step is not None, (
        "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    )
    run = finalize_step.get("run") or ""
    assert re.search(r"git rev-parse HEAD", run), (
        "The finalize step must read the current HEAD via `git rev-parse HEAD`"
    )
    assert re.search(r"!=.{0,40}PRE_AGENT_HEAD|PRE_AGENT_HEAD.{0,40}!=", run, re.DOTALL), (
        "The finalize step must compare current HEAD against PRE_AGENT_HEAD "
        "and exit before reaching the decline branch when a fix commit exists"
    )


def test_finalize_step_wires_fixer_outcome_and_pre_agent_head_via_env() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert finalize_step is not None, (
        "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    )
    env = finalize_step.get("env") or {}
    assert "steps.fixer.outcome" in str(env.get("FIXER_OUTCOME", "")), (
        "The finalize step's `env:` must wire a FIXER_OUTCOME-shaped key from `steps.fixer.outcome`"
    )
    assert "steps.setup.outputs.pre_agent_head" in str(env.get("PRE_AGENT_HEAD", "")), (
        "The finalize step's `env:` must wire a PRE_AGENT_HEAD-shaped key from "
        "`steps.setup.outputs.pre_agent_head`"
    )


def test_finalize_step_fails_closed_on_a_gh_label_read_error() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert finalize_step is not None, (
        "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    )
    run = finalize_step.get("run") or ""
    assert re.search(r"gh pr view.*--json labels.*2>/dev/null", run) or re.search(
        r"if\s*!\s*declined=", run
    ), (
        "The label-read command must fail CLOSED on a `gh` error (e.g. "
        "`2>/dev/null` behind an `if ! declined=...` guard), mirroring the "
        "`gate` step's fail-closed pattern, rather than crashing or "
        "blind-declining"
    )


def test_finalize_step_is_scoped_to_the_fixing_surfaces() -> None:
    """The finalize/decline step belongs only to surfaces that actually
    attempt a fix, and must never appear on `autofix-fork`.

    Originally this guard excluded the main-branch `autofix` job too, because
    the change it was written for deliberately left that job untouched. That
    scope has since been widened by a separate, deliberate decision: the
    `autofix` job's agent step gained `continue-on-error`, so a turn-budget
    crash no longer fails the job, and it needs the same finalize step to
    convert that crash into a countable decline. Without one, the crash would
    vanish from both the run-conclusion failure count and the decline count —
    a fixer degrading while every metric improved.

    `autofix-fork` stays excluded on a structural ground, not a scoping one:
    it holds `contents: read`, cannot push, and is suggest-only. It produces
    no fix, so it has no terminal fix state to decline, and a decline record
    there would count an event that never had a chance to occur.
    """
    parsed = _parsed()
    for job_name in ("autofix", "autofix-same-repo-pr"):
        assert _finalize_step(_job(parsed, job_name)) is not None, (
            f"The `{job_name}` job must carry the finalize/decline step — its agent runs under "
            "continue-on-error, so without finalize a crash is silently uncounted"
        )
    fork = _job(parsed, "autofix-fork")
    assert _finalize_step(fork) is None, (
        "The `autofix-fork` job must never gain the finalize/decline step — it is suggest-only "
        "(contents: read) and produces no fix, so it has no terminal fix state to decline"
    )
    assert (fork.get("permissions") or {}).get("contents") == "read", (
        "The `autofix-fork` exclusion above rests on the job being suggest-only; if it ever "
        "gains write access that reasoning no longer holds and the exclusion must be revisited"
    )
