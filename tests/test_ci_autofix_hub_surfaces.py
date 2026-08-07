"""Structural invariants for the ci-autofix hub's three surface jobs.

Covers the `classify` router (which reads the caller policy and
`github.event` once and emits a `surface` output), the `autofix-same-repo-pr`
job (fix-commit to a human/Dependabot PR's own head branch), and the
`autofix-fork` job (suggest-only, inverted read-only privilege). Each job's
privilege grant, agent allowlist, non-agent gate steps, and log-handling
contract are pinned here.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps and gates. It cannot verify runtime behavior (what
actually happens on a live run); where a test is a structural proxy for a
runtime guarantee, its docstring says so explicitly, and the guarantee closes
via dogfooding once Praxion's own caller exercises the hub in production CI.

Every test reads the workflow lazily (inside the function body, never at module
import time) so collection succeeds even when the file is absent — an absent
hub then fails with a clear assertion, never an import error.

Scope boundary (dogfood-only — no structural test is fabricated for these):
this suite cannot verify that a fix-commit loop stays bounded across
multiple real CI runs, that a genuinely unfixable dependency bump is
classified and left uncommitted end-to-end, or that a probe-of-the-default-
branch gate correctly declines when that branch is itself failing. Those are
runtime properties validated by a live dogfood against real pull requests,
not by parsing this YAML file.

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


def _claude_args(step: dict) -> str:
    """Return a claude-code-action step's `with.claude_args` block (the `--allowedTools` carrier)."""
    return (step.get("with") or {}).get("claude_args", "") or ""


def _job_text(job: dict) -> str:
    """Flatten a job's step names, shell bodies, and agent prompts into one search haystack."""
    parts: list[str] = []
    for step in job.get("steps") or []:
        parts.append(step.get("name", "") or "")
        parts.append(step.get("run", "") or "")
        parts.append((step.get("with") or {}).get("prompt", "") or "")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# `classify` job (new) — reads policy + github.event once, emits `surface`
# ---------------------------------------------------------------------------


def test_classify_job_exists() -> None:
    parsed = _parsed()
    assert "classify" in (parsed.get("jobs") or {}), (
        "A `classify` job must exist to read the caller policy and "
        "github.event once and emit a `surface` output for the new "
        "PR/Dependabot/fork surface jobs"
    )


def test_classify_job_reads_the_caller_policy_in_a_non_agent_step() -> None:
    parsed = _parsed()
    job = _job(parsed, "classify")
    policy_steps = [
        step
        for step in job.get("steps") or []
        if "autofix-policy" in (step.get("run") or "") or "policy_path" in (step.get("run") or "")
    ]
    assert policy_steps, "classify must read the caller's autofix-policy.yml in a plain `run:` step"
    for step in policy_steps:
        assert "uses" not in step, (
            "The policy-read step in `classify` must be a non-agent `run:` step"
        )


def test_classify_job_distinguishes_same_repo_from_fork_by_repository_fields() -> None:
    """Structural proxy: the classification logic must inspect
    `head_repository` vs `repository` to tell a same-repo PR from a fork PR,
    and must distinguish the Dependabot actor from other same-repo authors.
    The exact variable names/mechanism are an implementer choice.
    """
    parsed = _parsed()
    job = _job(parsed, "classify")
    job_run_text = " ".join(step.get("run", "") or "" for step in job.get("steps") or [])
    assert "head_repository" in job_run_text, (
        "classify must inspect github.event.workflow_run.head_repository to "
        "distinguish same-repo PRs from fork PRs"
    )
    assert re.search(r"dependabot", job_run_text, re.IGNORECASE), (
        "classify must distinguish the Dependabot actor from other same-repo PR authors"
    )


def test_classify_job_emits_a_surface_output() -> None:
    parsed = _parsed()
    job = _job(parsed, "classify")
    outputs = job.get("outputs") or {}
    assert "surface" in outputs, (
        "`classify` must declare a job-level `surface` output so downstream "
        "surface jobs (via `needs: classify`) can gate on it"
    )


# ---------------------------------------------------------------------------
# `autofix-same-repo-pr` job (new) — fix-commit to the PR's own head branch
# ---------------------------------------------------------------------------


def test_autofix_same_repo_pr_job_exists() -> None:
    parsed = _parsed()
    assert "autofix-same-repo-pr" in (parsed.get("jobs") or {}), (
        "An `autofix-same-repo-pr` job must exist to fix-commit same-repo "
        "human-PR and Dependabot-PR CI failures to the PR's own head branch"
    )


def test_autofix_same_repo_pr_agent_allowlist_excludes_branch_movement_and_push() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    for step in agent_steps:
        allowed_tools = _claude_args(step)
        assert "git checkout" not in allowed_tools, (
            "The fixer's allowlist must not grant `git checkout` — the PR "
            "head is positioned by a non-agent step, not the agent"
        )
        assert "git branch" not in allowed_tools, (
            "The fixer's allowlist must not grant `git branch`"
        )
        assert "git push" not in allowed_tools, (
            "The fixer's allowlist must not grant `git push` — pushing the "
            "fix commit is a non-agent step's responsibility"
        )


def test_autofix_same_repo_pr_agent_allowlist_excludes_pr_merge() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    for step in agent_steps:
        assert "gh pr merge" not in _claude_args(step), (
            "The fixer's allowlist must not grant `gh pr merge` — a human always owns the merge decision"
        )


def test_autofix_same_repo_pr_allowlists_only_dependabot_bot() -> None:
    """The dependabot surface reacts to Dependabot-initiated workflow_run events;
    claude-code-action blocks bot-initiated runs by default, so the fixer step must
    allowlist dependabot[bot] to act on them — scoped, never '*' (which the action
    warns would let external Apps invoke it on this public repo)."""
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    for step in agent_steps:
        allowed = str(step.get("with", {}).get("allowed_bots", ""))
        assert "dependabot[bot]" in allowed, (
            "The fixer must allowlist dependabot[bot] or the dependabot surface is DOA (agent never runs)"
        )
        assert allowed.strip() != "*", (
            "Never allow all bots ('*') on a public repo — the action warns against it"
        )


def test_autofix_same_repo_pr_fetches_and_sanitizes_failure_logs_in_a_non_agent_step() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    fetch_steps = [
        step
        for step in job.get("steps") or []
        if "gh run view" in (step.get("run") or "") and "log" in (step.get("run") or "").lower()
    ]
    assert fetch_steps, (
        "autofix-same-repo-pr must fetch the failed run's logs via a plain "
        "shell step, writing them to a file the agent reads as DATA"
    )
    for step in fetch_steps:
        assert "uses" not in step, (
            "The log-fetch step must be a `run:` step, not an agent action — "
            "logs must never be interpolated directly into the agent's prompt"
        )


def test_autofix_same_repo_pr_prompt_frames_logs_as_untrusted_data() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    for step in agent_steps:
        prompt = (step.get("with") or {}).get("prompt", "") or ""
        assert re.search(r"untrusted", prompt, re.IGNORECASE), (
            "The fixer's own prompt must frame fetched CI log content as untrusted data"
        )
        assert re.search(r"instruction", prompt, re.IGNORECASE), (
            "The fixer's own prompt must distinguish log content from instructions"
        )


def test_autofix_same_repo_pr_gates_on_an_attempt_counter_commit_trailer() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    gate_steps = [
        step
        for step in job.get("steps") or []
        if "Autofix-Attempt" in (step.get("run") or "")
        and "max_attempts_per_pr" in (step.get("run") or "")
    ]
    assert gate_steps, (
        "A non-agent step must count `Autofix-Attempt:` commit trailers on "
        "the PR branch and compare against `max_attempts_per_pr` to bound "
        "the fix-commit loop"
    )


def test_autofix_same_repo_pr_stamps_the_attempt_trailer_from_a_non_agent_step() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    stamp_steps = [
        step
        for step in job.get("steps") or []
        if "Autofix-Attempt:" in (step.get("run") or "") and "git commit" in (step.get("run") or "")
    ]
    assert stamp_steps, (
        "The `Autofix-Attempt: N` trailer must be stamped by a non-agent "
        "commit step, never by the agent, so the counter can never be missed"
    )
    for step in stamp_steps:
        assert "uses" not in step, "The trailer-stamping step must be a non-agent `run:` step"


def test_autofix_same_repo_pr_declines_idempotently_via_a_terminal_label() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    assert "autofix:declined" in _job_text(job), (
        "An `autofix:declined` label must gate re-arming the fixer (idempotency) on an already-declined PR"
    )


def test_autofix_same_repo_pr_pushes_without_force_to_the_pr_head_branch() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    push_steps = [
        step
        for step in job.get("steps") or []
        if "git push origin HEAD:" in (step.get("run") or "")
    ]
    assert push_steps, (
        "A non-agent step must push the fix commit via `git push origin "
        "HEAD:<head-branch>` — the PR's own head, never an implicit push"
    )
    for step in push_steps:
        assert "--force" not in (step.get("run") or ""), (
            "The push must never use `--force` — a rejected push (non-fast-"
            "forward or permission/read-only) must skip-and-flag instead"
        )


def test_autofix_same_repo_pr_includes_a_sensitive_path_tripwire_step() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    assert "sensitive" in _job_text(job).lower(), (
        "autofix-same-repo-pr must include its own sensitive-path tripwire "
        "step, converting the PR to draft when a fix touches CI/automation surfaces"
    )


# ---------------------------------------------------------------------------
# `autofix-fork` job (new) — suggest-only, inverted (read-only) privilege
# ---------------------------------------------------------------------------


def test_autofix_fork_job_exists() -> None:
    parsed = _parsed()
    assert "autofix-fork" in (parsed.get("jobs") or {}), (
        "An `autofix-fork` job must exist to post suggest-only patch comments on fork PR CI failures"
    )


def test_autofix_fork_job_grants_read_only_contents_permission() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-fork")
    permissions = job.get("permissions") or {}
    assert permissions.get("contents") == "read", (
        "autofix-fork must hold `contents: read` — no write grant to an "
        "untrusted fork head, even for a compromised agent step"
    )


def test_autofix_fork_agent_allowlist_grants_no_write_or_git_or_merge() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-fork")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-fork must contain a claude-code-action suggest-only step"
    for step in agent_steps:
        allowed_tools = _claude_args(step)
        assert "Edit" not in allowed_tools, (
            "The fork suggest-only fixer's allowlist must not grant `Edit`"
        )
        assert "Write" not in allowed_tools, (
            "The fork suggest-only fixer's allowlist must not grant `Write`"
        )
        assert not re.search(r"Bash\(git", allowed_tools), (
            "The fork suggest-only fixer's allowlist must not grant any git subcommand — it never commits"
        )
        assert "gh pr merge" not in allowed_tools, (
            "The fork suggest-only fixer's allowlist must not grant `gh pr merge`"
        )
        assert "gh pr comment" in allowed_tools, (
            "The fork suggest-only fixer must be able to post a suggested-patch comment via `gh pr comment`"
        )


def test_autofix_fork_grants_no_bash_execution_scoped_to_the_isolated_checkout() -> None:
    """If the fork job checks the fork head out into an isolated directory
    (a `pr-head` subdirectory), the agent may read it via `--add-dir` but the
    allowlist must never contain a Bash pattern that could execute anything
    from within it.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-fork")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-fork must contain a claude-code-action suggest-only step"
    for step in agent_steps:
        assert not re.search(r"Bash\([^)]*pr-head", _claude_args(step)), (
            "The fork job must never grant Bash execution scoped to "
            "`pr-head` — isolated fork content may be read, never executed"
        )


def test_autofix_fork_gates_on_the_daily_run_budget() -> None:
    """Even though the fork surface is suggest-only, each fork agent run still
    counts toward the caller workflow's shared daily run tally — so it must
    enforce the same daily run-budget cap as the other fix surfaces via a
    non-agent gate step, or an uncapped fork job could inflate the count and
    starve the privileged surfaces of their budget.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-fork")
    budget_steps = [
        step
        for step in job.get("steps") or []
        if "runs_today" in (step.get("run") or "") and "MAX_RUNS_PER_DAY" in (step.get("run") or "")
    ]
    assert budget_steps, (
        "autofix-fork must include a non-agent step that counts today's runs "
        "and compares them against the daily run-budget cap before invoking "
        "the fixer agent"
    )
    for step in budget_steps:
        assert "uses" not in step, (
            "The budget gate must be a non-agent `run:` step, evaluated before the fixer agent runs"
        )
