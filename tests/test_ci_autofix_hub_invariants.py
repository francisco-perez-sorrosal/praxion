"""Structural invariant tests for the hub reusable workflow.

`.github/workflows/reusable-ci-autofix.yml` does not exist yet — these tests
define the security/interface contract the implementer must satisfy when
generalizing the shipped `ci-autofix.yml` into a public `on: workflow_call`
hub. Every test reads the file lazily (inside the function body, not at
module import time) so collection succeeds before the file exists; running
this module now is expected to fail with a clear "file not found" assertion
(RED), not an import error.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps and gates. It cannot verify runtime behavior (e.g.
what actually happens when a real `autofix-policy.yml` is missing on a live
run) — that closes via dogfooding once Praxion's own caller exercises the hub
in production CI. Where a test is a structural proxy for a runtime guarantee,
its docstring says so explicitly.

Extension (this module, later section): the hub above already exists and
ships a single `autofix` job (main-branch fix-PR). The later section of this
file defines structural contracts for three NEW jobs — a classifier plus a
same-repo (human-PR/Dependabot) fix-commit job and a fork suggest-only job —
that do not exist in the file yet. Those assertions are expected to fail on
the first run (job absent / empty step collections / missing job output),
never with a collection or import error.

Further extension (this module, final section): `classify`'s single coupled
`JS_RUNNER_TABLE` (enum -> install+runner pair) is split into a runner-only
table plus a new `JS_PM_INSTALL` table keyed on a package manager detected
from the trusted default-branch lockfile (`detect_pm`); the install step
gains an addressable `id` and `continue-on-error`; the fixer step's gate is
extended to skip when the install step fails. Some assertions here execute
the classify step's embedded Python script directly (extracted from its
`run:` text into a temp file, run against a fixture directory) rather than
pattern-matching source text — the strongest available proxy for "detection
reads the declared project dir, not wherever the job happens to run", since
that is precisely the mechanism the #48 dogfood broke. A few of these
(flagged individually) are naturally satisfied by today's simpler
always-`npm ci` behavior and only bite as regression guards once `detect_pm`
lands — not TDD-red assertions.

Scope boundary (dogfood-only — no structural test is fabricated for these):
this suite cannot verify that a fix-commit loop stays bounded across
multiple real CI runs, that a genuinely unfixable dependency bump is
classified and left uncommitted end-to-end, or that a probe-of-the-default-
branch gate correctly declines when that branch is itself failing. Those are
runtime properties validated by a live dogfood against real pull requests,
not by parsing this YAML file.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HUB_WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "reusable-ci-autofix.yml"

SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_text() -> str:
    """Return the hub workflow's raw file content (read lazily so collection succeeds)."""
    return HUB_WORKFLOW_FILE.read_text(encoding="utf-8")


def _parsed() -> dict:
    """Parse the hub workflow as YAML."""
    return yaml.safe_load(_raw_text())


def _on_block(parsed: dict) -> dict:
    """Return the `on:` trigger block.

    PyYAML's default (YAML 1.1) resolver treats the bare scalar `on` as the
    boolean `True` — including when it appears as a mapping key — so a
    top-level `on:` block parses under the key `True`, not the string `"on"`.
    This is a well-known GitHub-Actions-YAML gotcha; every lookup of the
    trigger block must account for it.
    """
    if "on" in parsed:
        return parsed["on"]
    if True in parsed:
        return parsed[True]
    raise AssertionError("Hub workflow has no `on:` trigger block")


def _all_steps(parsed: dict) -> list[dict]:
    """Flatten every step across every job in the workflow."""
    steps: list[dict] = []
    for job in (parsed.get("jobs") or {}).values():
        steps.extend(job.get("steps") or [])
    return steps


def _uses_refs(parsed: dict) -> list[str]:
    """Collect every `uses:` value across every job/step in the workflow."""
    return [step["uses"] for step in _all_steps(parsed) if step.get("uses")]


def _policy_read_step(parsed: dict) -> dict | None:
    """Return the first step whose body references reading the caller's policy file."""
    for step in _all_steps(parsed):
        haystack = f"{step.get('name', '')} {step.get('run', '')}"
        if "autofix-policy" in haystack or "policy_path" in haystack:
            return step
    return None


def _mentions_default_near(raw: str, field: str, window: int = 400) -> bool:
    """True if `field` and a "default" marker co-occur within `window` chars, either order.

    A loose structural proxy: it does not pin the exact parsing mechanism
    (yq/jq/python), only that a safe-default value is documented/wired near
    the field name.
    """
    pattern = re.compile(
        rf"({re.escape(field)}.{{0,{window}}}default|default.{{0,{window}}}{re.escape(field)})",
        re.IGNORECASE | re.DOTALL,
    )
    return bool(pattern.search(raw))


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
# Existence and parseability
# ---------------------------------------------------------------------------


def test_hub_workflow_file_exists_and_parses_as_yaml() -> None:
    assert HUB_WORKFLOW_FILE.exists(), (
        f"{HUB_WORKFLOW_FILE} not found. The implementer must create the hub "
        "reusable workflow generalizing the shipped ci-autofix.yml."
    )
    parsed = _parsed()
    assert isinstance(parsed, dict), "Hub workflow must parse to a YAML mapping"


# ---------------------------------------------------------------------------
# workflow_call interface (caller-facing contract)
# ---------------------------------------------------------------------------


def test_hub_declares_workflow_call_trigger() -> None:
    parsed = _parsed()
    on_block = _on_block(parsed)
    assert "workflow_call" in on_block, (
        "Hub workflow's `on:` block must declare `workflow_call` — it is invoked "
        "exclusively as a reusable workflow, never triggered directly"
    )


def test_workflow_call_declares_policy_path_input_with_safe_default() -> None:
    parsed = _parsed()
    workflow_call = _on_block(parsed)["workflow_call"]
    inputs = workflow_call.get("inputs", {}) or {}
    assert "policy_path" in inputs, (
        "on.workflow_call.inputs must declare `policy_path` — the caller's per-repo "
        "policy file location must be sourced through the interface, never hardcoded"
    )
    assert (
        inputs["policy_path"].get("default") == ".github/autofix-policy.yml"
    ), "`policy_path` input must default to '.github/autofix-policy.yml'"


def test_workflow_call_declares_required_oauth_secret() -> None:
    parsed = _parsed()
    workflow_call = _on_block(parsed)["workflow_call"]
    secrets_block = workflow_call.get("secrets", {}) or {}
    assert (
        "CLAUDE_CODE_OAUTH_TOKEN" in secrets_block
    ), "on.workflow_call.secrets must declare CLAUDE_CODE_OAUTH_TOKEN"
    assert secrets_block["CLAUDE_CODE_OAUTH_TOKEN"].get("required") is True, (
        "CLAUDE_CODE_OAUTH_TOKEN must be declared `required: true` — a caller "
        "invoking the hub without this secret must fail loudly, not silently"
    )


def test_never_uses_secrets_inherit() -> None:
    raw = _raw_text()
    assert "secrets: inherit" not in raw, (
        "`secrets: inherit` must never appear in the hub — it silently no-ops "
        "cross-org auth (works same-org, breaks every managed repo in a different "
        "org); secrets must be passed by explicit mapping only"
    )


# ---------------------------------------------------------------------------
# Banned patterns (carried-over P0 security invariants)
# ---------------------------------------------------------------------------


def test_never_references_track_progress() -> None:
    raw = _raw_text()
    assert "track_progress" not in raw, "`track_progress` must never appear in the hub"


def test_never_triggers_on_pull_request_target() -> None:
    raw = _raw_text()
    assert (
        "pull_request_target" not in raw
    ), "`pull_request_target` must never appear anywhere in the hub"


# ---------------------------------------------------------------------------
# Supply-chain pinning
# ---------------------------------------------------------------------------


def test_every_uses_reference_is_sha_pinned() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    assert refs, (
        "Hub workflow must contain at least one `uses:` step "
        "(checkout, setup-uv, the diagnosing agent action)"
    )
    for ref in refs:
        assert "@" in ref, f"`uses: {ref}` must pin a ref via '@<sha>'"
        pinned_ref = ref.rsplit("@", 1)[1]
        assert SHA_PIN_PATTERN.match(pinned_ref), (
            f"`uses: {ref}` must be pinned to a full 40-hex-char commit SHA, "
            f"not a mutable tag or branch (got {pinned_ref!r})"
        )


# ---------------------------------------------------------------------------
# Loop prevention (layered — every layer from the shipped workflow must survive)
# ---------------------------------------------------------------------------


def test_declares_a_concurrency_group() -> None:
    parsed = _parsed()
    assert "concurrency" in parsed, (
        "Hub workflow must declare a top-level `concurrency:` group so two "
        "autofix runs never race to open conflicting PRs"
    )
    assert parsed["concurrency"].get("group"), "`concurrency:` block must declare a `group:` key"


def test_job_gates_on_failure_conclusion() -> None:
    parsed = _parsed()
    jobs = parsed.get("jobs") or {}
    assert jobs, "Hub workflow must declare at least one job"
    conditions = [job.get("if") or "" for job in jobs.values()]
    assert any(
        "conclusion" in c and "failure" in c for c in conditions
    ), "At least one job must gate on the failed run's `conclusion == 'failure'`"


def test_branch_gate_uses_default_branch_not_hardcoded_main() -> None:
    raw = _raw_text()
    assert "default_branch" in raw, (
        "The branch gate must reference github.event.repository.default_branch — "
        "generalizing the shipped workflow's hardcoded 'main' so the hub works on "
        "managed repos whose default branch is not 'main'"
    )
    assert not re.search(
        r"head_branch\s*==\s*['\"]main['\"]", raw
    ), "The branch gate must not hardcode `head_branch == 'main'`"


def test_dedup_step_skips_when_autofix_pr_already_open() -> None:
    parsed = _parsed()
    dedup_candidates = [
        step
        for step in _all_steps(parsed)
        if "headRefName" in (step.get("run") or "") and "ci-autofix/" in (step.get("run") or "")
    ]
    assert dedup_candidates, (
        "A dedup step must list open PRs and skip diagnosis when one already "
        "targets the ci-autofix/ branch prefix"
    )


# ---------------------------------------------------------------------------
# Sanitized-logs-as-data
# ---------------------------------------------------------------------------


def test_log_fetch_step_is_non_agent_and_reads_logs_as_plain_shell_output() -> None:
    parsed = _parsed()
    fetch_steps = [
        step
        for step in _all_steps(parsed)
        if "gh run view" in (step.get("run") or "") and "log" in (step.get("run") or "").lower()
    ]
    assert fetch_steps, (
        "A plain shell step must fetch the failed run's logs via "
        "`gh run view ... --log-failed` (or equivalent), not an agent action"
    )
    for step in fetch_steps:
        assert "uses" not in step, (
            "The log-fetch step must be a `run:` step, not a `uses:` agent action — "
            "logs are written to a file for the agent to read as DATA, never "
            "interpolated directly into an agent's instructions"
        )


def test_log_fetch_output_is_sanitized_before_the_agent_reads_it() -> None:
    """Structural proxy: asserts sanitization is documented OR mechanically
    performed somewhere in the workflow — either descriptive prose (sanitize/
    truncate/strip) or the actual shell mechanism (an ANSI-escape strip via a
    literal `\\x1b` pattern, or a character-count truncation via `cut -c`/
    `head -c`). The exact mechanism is an implementer choice.
    """
    raw = _raw_text()
    assert re.search(r"saniti|truncat|\\x1b|cut -c|head -c|strip", raw, re.IGNORECASE), (
        "The fetched log content must be sanitized (e.g. stripped of ANSI escape "
        "codes, truncated per line) before the agent reads it as data"
    )


def test_agent_prompt_frames_log_content_as_untrusted_data() -> None:
    raw = _raw_text()
    assert re.search(r"untrusted", raw, re.IGNORECASE), (
        "The agent-facing prompt must explicitly frame fetched CI log content as "
        "untrusted data (prompt-injection mitigation)"
    )
    assert re.search(r"instruction", raw, re.IGNORECASE), (
        "The agent-facing prompt must explicitly distinguish log content from "
        "instructions (prompt-injection mitigation)"
    )


# ---------------------------------------------------------------------------
# Sensitive-path tripwire
# ---------------------------------------------------------------------------


def test_sensitive_path_tripwire_step_exists() -> None:
    parsed = _parsed()
    steps = _all_steps(parsed)
    step_names = " ".join((step.get("name") or "").lower() for step in steps)
    step_runs = " ".join((step.get("run") or "").lower() for step in steps)
    assert "sensitive" in step_names or "sensitive" in step_runs, (
        "A sensitive-path tripwire step must exist, converting a PR to draft and "
        "requesting mandatory human review when it touches CI/automation surfaces"
    )


def test_sensitive_path_tripwire_sources_paths_from_policy() -> None:
    raw = _raw_text()
    assert "sensitive_paths" in raw, (
        "The tripwire step must source its sensitive-path list from the caller's "
        "policy file (policy.safety.sensitive_paths), not a hardcoded list"
    )


# ---------------------------------------------------------------------------
# Plugin-dir generalization (a managed caller's checked-out repo generally
# has no .claude-plugin/plugin.json, so this must never be a static literal)
# ---------------------------------------------------------------------------


def test_plugin_dir_reaches_claude_args_only_through_the_policy_output() -> None:
    parsed = _parsed()
    diagnose_steps = [
        step for step in _all_steps(parsed) if "claude-code-action" in (step.get("uses") or "")
    ]
    assert diagnose_steps, "Expected the claude-code-action diagnose step to exist"
    for step in diagnose_steps:
        claude_args = (step.get("with") or {}).get("claude_args", "")
        assert not re.search(r"^\s*--plugin-dir\s+\.\s*$", claude_args, re.MULTILINE), (
            "`claude_args` must not hardcode `--plugin-dir .` as a static line — a "
            "managed caller's checked-out repo generally has no "
            ".claude-plugin/plugin.json, so this would error or drop context for "
            "every managed caller"
        )
        assert "plugin_dir_flag" in claude_args, (
            "plugin-dir must reach `claude_args` via the policy step's "
            "`plugin_dir_flag` output (provider.plugin_dir, no default — absent "
            "omits the flag), not a static literal"
        )


# ---------------------------------------------------------------------------
# Policy-fails-safe (structural proxy — see module docstring)
# ---------------------------------------------------------------------------


def test_policy_read_step_exists() -> None:
    parsed = _parsed()
    assert (
        _policy_read_step(parsed) is not None
    ), "Hub must contain a non-agent step that reads/parses the caller's autofix-policy.yml"


def test_missing_or_malformed_policy_falls_back_to_a_safe_tripwire_default() -> None:
    """Structural proxy for fail-open-but-fail-SAFE policy handling.

    True runtime behavior (a live run against a genuinely absent/garbled
    policy file) is not exercised here — verified by dogfooding/live CI.
    """
    raw = _raw_text()
    assert _mentions_default_near(raw, "sensitive_paths"), (
        "A missing/malformed policy must not silently disable the sensitive-path "
        "tripwire — a safe default value must be defined near sensitive_paths"
    )


def test_missing_or_malformed_policy_falls_back_to_a_safe_budget_cap() -> None:
    """Structural proxy — see test_missing_or_malformed_policy_falls_back_to_a_safe_tripwire_default."""
    raw = _raw_text()
    assert _mentions_default_near(raw, "max_runs_per_day"), (
        "A missing/malformed policy must not silently uncap daily runs — a safe "
        "default value must be defined near max_runs_per_day"
    )


def test_missing_or_malformed_policy_falls_back_to_a_safe_surface_toggle() -> None:
    """Structural proxy — see test_missing_or_malformed_policy_falls_back_to_a_safe_tripwire_default."""
    raw = _raw_text()
    assert _mentions_default_near(raw, "main_branch"), (
        "A missing/malformed policy must not silently leave the main-branch "
        "fix-pr surface in an undefined state — a safe default value must be "
        "defined near surfaces.main_branch"
    )


# ---------------------------------------------------------------------------
# Main-path preservation (byte-stability anchor for the P3a extension below)
# ---------------------------------------------------------------------------


def test_existing_autofix_job_is_unchanged_by_the_new_surface_jobs() -> None:
    """Anchor for the byte-stability guarantee: the pre-existing `autofix`
    job's gate condition, privilege grant, and step sequence must survive
    the new surface jobs' addition completely unmodified.
    """
    parsed = _parsed()
    jobs = parsed.get("jobs") or {}
    assert "autofix" in jobs, "The pre-existing `autofix` job must still exist"
    autofix_job = jobs["autofix"]
    condition = autofix_job.get("if") or ""
    assert (
        "head_branch == github.event.repository.default_branch" in condition
    ), "The `autofix` job's branch gate must remain unchanged"
    assert (
        autofix_job.get("permissions", {}).get("contents") == "write"
    ), "The `autofix` job's `contents: write` grant must remain unchanged"
    step_names = [step.get("name") for step in autofix_job.get("steps") or []]
    # The finalize/decline step was added later and deliberately, by a separate
    # decision from the surface-addition work this guard was written for: the
    # agent step now carries `continue-on-error`, so a turn-budget crash no
    # longer fails the job, and finalize converts that crash into a countable
    # decline. The guard's purpose is unchanged — it still pins the sequence so
    # a future surface addition cannot silently perturb this job.
    assert step_names == [
        "Checkout caller repo's default branch",
        "Set up uv (manages Python 3.13)",
        "Read autofix policy (fail-safe defaults)",
        "Enforce daily run budget",
        "Skip if an autofix PR is already open",
        "Fetch failure logs (non-agent, untrusted output)",
        "Diagnose failure and open a fix PR",
        "Finalize terminal state (decline if the fixer crashed)",
        "Flag sensitive-path changes for review",
    ], "The `autofix` job's step sequence must remain byte-identical"


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
        assert (
            "uses" not in step
        ), "The policy-read step in `classify` must be a non-agent `run:` step"


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
    assert re.search(
        r"dependabot", job_run_text, re.IGNORECASE
    ), "classify must distinguish the Dependabot actor from other same-repo PR authors"


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
        assert (
            "git branch" not in allowed_tools
        ), "The fixer's allowlist must not grant `git branch`"
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
        assert (
            "gh pr merge" not in _claude_args(step)
        ), "The fixer's allowlist must not grant `gh pr merge` — a human always owns the merge decision"


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
        assert (
            "dependabot[bot]" in allowed
        ), "The fixer must allowlist dependabot[bot] or the dependabot surface is DOA (agent never runs)"
        assert (
            allowed.strip() != "*"
        ), "Never allow all bots ('*') on a public repo — the action warns against it"


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
        assert re.search(
            r"untrusted", prompt, re.IGNORECASE
        ), "The fixer's own prompt must frame fetched CI log content as untrusted data"
        assert re.search(
            r"instruction", prompt, re.IGNORECASE
        ), "The fixer's own prompt must distinguish log content from instructions"


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
    assert (
        "autofix:declined" in _job_text(job)
    ), "An `autofix:declined` label must gate re-arming the fixer (idempotency) on an already-declined PR"


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
    assert "autofix-fork" in (
        parsed.get("jobs") or {}
    ), "An `autofix-fork` job must exist to post suggest-only patch comments on fork PR CI failures"


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
        assert (
            "Edit" not in allowed_tools
        ), "The fork suggest-only fixer's allowlist must not grant `Edit`"
        assert (
            "Write" not in allowed_tools
        ), "The fork suggest-only fixer's allowlist must not grant `Write`"
        assert not re.search(
            r"Bash\(git", allowed_tools
        ), "The fork suggest-only fixer's allowlist must not grant any git subcommand — it never commits"
        assert (
            "gh pr merge" not in allowed_tools
        ), "The fork suggest-only fixer's allowlist must not grant `gh pr merge`"
        assert (
            "gh pr comment" in allowed_tools
        ), "The fork suggest-only fixer must be able to post a suggested-patch comment via `gh pr comment`"


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
        assert (
            "uses" not in step
        ), "The budget gate must be a non-agent `run:` step, evaluated before the fixer agent runs"


# ---------------------------------------------------------------------------
# Cross-cutting (P3a) — concurrency scoping and pin auditability
# ---------------------------------------------------------------------------


def test_concurrency_group_is_scoped_per_branch_not_shared_across_the_repo() -> None:
    """A single repo-wide group would race one PR's fix-commit run against
    unrelated runs on other branches; a per-branch dynamic group keeps
    main's own runs serializing among themselves (behavior-identical to
    today) while different PRs fix in parallel.
    """
    parsed = _parsed()
    group = (parsed.get("concurrency") or {}).get("group") or ""
    assert "head_branch" in group, (
        "The concurrency group must interpolate the failed run's head "
        "branch (e.g. `ci-autofix-${{ github.event.workflow_run.head_branch "
        "}}`) so different PRs fix in parallel while main's own runs still "
        "serialize among themselves"
    )


def test_every_uses_reference_carries_a_version_comment() -> None:
    """SHA pins are unreadable without a version anchor — every `uses:`
    line must carry a trailing `# vX.Y.Z` (or `# v<major>`) comment so a
    human bumping the pin knows which release it corresponds to, matching
    the convention already used throughout this workflow.
    """
    raw = _raw_text()
    uses_lines = [line for line in raw.splitlines() if re.search(r"uses:\s*\S+@[0-9a-f]{40}", line)]
    assert uses_lines, "Expected at least one SHA-pinned `uses:` line"
    for line in uses_lines:
        assert re.search(r"#\s*v\d+(\.\d+){0,2}", line), (
            f"{line.strip()!r} must carry a trailing version comment "
            "(`# vX.Y.Z` or `# v<major>`) for auditability"
        )


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


def _finalize_step(job: dict) -> dict | None:
    """Return the non-agent finalize/decline step in a job, or `None` if it
    does not exist yet (RED-safe)."""
    for step in job.get("steps") or []:
        if "finalize" in (step.get("name") or "").lower():
            return step
    return None


def _all_agent_steps(parsed: dict) -> list[dict]:
    """Return every `claude-code-action` step across every job in the workflow."""
    return [step for step in _all_steps(parsed) if "claude-code-action" in (step.get("uses") or "")]


def _allowed_tools_value(step: dict) -> str | None:
    """Extract the quoted value of `--allowedTools "..."` from a step's `claude_args`."""
    match = re.search(r'--allowedTools "([^"]*)"', _claude_args(step))
    return match.group(1) if match else None


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
    assert (
        finalize_step is not None
    ), "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    assert "uses" not in finalize_step, "The finalize step must be a non-agent `run:` step"
    push_index = next(i for i, name in enumerate(step_names) if "push" in name.lower())
    tripwire_index = next(i for i, name in enumerate(step_names) if "sensitive" in name.lower())
    finalize_index = step_names.index(finalize_step.get("name", ""))
    assert (
        push_index < finalize_index < tripwire_index
    ), "The finalize step must run after the push step and before the sensitive-path tripwire step"


def test_finalize_step_is_guarded_on_always_and_budget_proceed() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert (
        finalize_step is not None
    ), "autofix-same-repo-pr must contain a non-agent finalize/decline step"
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
    assert (
        finalize_step is not None
    ), "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    run = finalize_step.get("run") or ""
    assert "PRE_AGENT_HEAD" in run, (
        "The finalize step must compare current HEAD against a "
        "PRE_AGENT_HEAD-shaped value to detect whether a fix commit exists"
    )
    assert re.search(r"gh pr view.*--json labels", run), (
        "The finalize step must read the PR's labels via `gh pr view ... "
        "--json labels` to check for an existing autofix:declined label"
    )
    assert (
        "gh pr comment" in run
    ), "The no-fix/no-label branch must post a bounded root-cause comment via `gh pr comment`"
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
    assert (
        finalize_step is not None
    ), "autofix-same-repo-pr must contain a non-agent finalize/decline step"
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
    assert (
        finalize_step is not None
    ), "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    run = finalize_step.get("run") or ""
    assert re.search(
        r"git rev-parse HEAD", run
    ), "The finalize step must read the current HEAD via `git rev-parse HEAD`"
    assert re.search(r"!=.{0,40}PRE_AGENT_HEAD|PRE_AGENT_HEAD.{0,40}!=", run, re.DOTALL), (
        "The finalize step must compare current HEAD against PRE_AGENT_HEAD "
        "and exit before reaching the decline branch when a fix commit exists"
    )


def test_finalize_step_wires_fixer_outcome_and_pre_agent_head_via_env() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert (
        finalize_step is not None
    ), "autofix-same-repo-pr must contain a non-agent finalize/decline step"
    env = finalize_step.get("env") or {}
    assert "steps.fixer.outcome" in str(
        env.get("FIXER_OUTCOME", "")
    ), "The finalize step's `env:` must wire a FIXER_OUTCOME-shaped key from `steps.fixer.outcome`"
    assert "steps.setup.outputs.pre_agent_head" in str(env.get("PRE_AGENT_HEAD", "")), (
        "The finalize step's `env:` must wire a PRE_AGENT_HEAD-shaped key from "
        "`steps.setup.outputs.pre_agent_head`"
    )


def test_finalize_step_fails_closed_on_a_gh_label_read_error() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    finalize_step = _finalize_step(job)
    assert (
        finalize_step is not None
    ), "autofix-same-repo-pr must contain a non-agent finalize/decline step"
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


def test_allowedtools_value_stays_a_single_physical_line_in_every_agent_step() -> None:
    """New general invariant (protects both Bug A's no-op case and Bug B's
    later token append): for every `claude-code-action` step across the
    whole workflow, the `--allowedTools "..."` value must never contain an
    embedded newline — a wrapped allowlist is silently narrowed at runtime
    (each newline-split fragment is parsed as its own, often malformed,
    comma-separated token). This is a source-text structural proxy: it
    cannot prove the *rendered* (post `${{ }}` substitution) line stays
    unwrapped at runtime — that closes via the live dogfood.

    Expected GREEN on first run: today's file already satisfies this
    invariant. This is a preventive regression guard, not a TDD-red
    assertion — call this out so it is not mistaken for a broken RED
    expectation.
    """
    parsed = _parsed()
    agent_steps = _all_agent_steps(parsed)
    assert agent_steps, "Expected at least one claude-code-action step in the workflow"
    for step in agent_steps:
        value = _allowed_tools_value(step)
        assert (
            value is not None
        ), f'Expected an --allowedTools "..." value in {step.get("name")!r}\'s claude_args'
        assert "\n" not in value, (
            f"{step.get('name')!r}'s --allowedTools value must stay a single "
            "physical line — a wrapped allowlist is silently narrowed at runtime"
        )


# ---------------------------------------------------------------------------
# Bug B — policy-gated JS/TS runner (enum-mapped allowlist grant)
#
# RED-phase note: every assertion below expects the shipped file, at time of
# writing, to lack the `js_test_runner` policy key, the classifier table, the
# new classify outputs, and the non-agent install step — expected failures
# are "output/step absent" shapes. `test_fixer_allowlist_contains_no_install_
# command_for_js_test_runner` is a negative/absence proxy (structurally
# identical in kind to the single-line invariant above): it cannot go RED
# before an install command could be added to the allowlist, and stays GREEN
# forever by design — flagged here rather than silently miscounted as a
# broken RED expectation.
# ---------------------------------------------------------------------------

BUG_A_BASELINE_ALLOWED_TOOLS = (
    "Read,Glob,Grep,Edit,Write,Bash(git add:*),Bash(git commit:*),Bash(git status:*),"
    "Bash(git diff:*),Bash(gh pr comment:*),Bash(gh pr diff:*),Bash(gh pr view:*),"
    "Bash(gh pr edit:*),Bash(uv run pytest:*),Bash(python3 -m pytest:*),Bash(pytest:*)"
)


def _classify_step(job: dict) -> dict | None:
    """Return the `classify` job's `id: classify` step, or `None` if absent."""
    return next((step for step in job.get("steps") or [] if step.get("id") == "classify"), None)


def test_classify_emits_js_install_cmd_and_js_test_grant_outputs() -> None:
    parsed = _parsed()
    job = _job(parsed, "classify")
    outputs = job.get("outputs") or {}
    assert "js_install_cmd" in outputs, (
        "`classify` must declare a job-level `js_install_cmd` output, "
        "sourced from steps.classify.outputs.js_install_cmd"
    )
    assert "js_test_grant" in outputs, (
        "`classify` must declare a job-level `js_test_grant` output, "
        "sourced from steps.classify.outputs.js_test_grant"
    )


def test_js_test_runner_enum_defaults_to_off_when_policy_key_absent() -> None:
    """Structural proxy: the classifier's `DEFAULTS` table must carry a safe
    "off" default for the JS/TS runner selector, mirroring the existing
    `pr_checks`/`dependabot`/`fork_prs` default-off pattern — a missing or
    malformed policy key must never silently activate the runner grant.
    """
    parsed = _parsed()
    job = _job(parsed, "classify")
    classify_step = _classify_step(job)
    assert classify_step is not None, "classify job must contain its `classify` step"
    run = classify_step.get("run") or ""
    assert _mentions_default_near(run, "js_test_runner"), (
        'The classifier\'s DEFAULTS table must define a safe default ("off") '
        "for js_test_runner, matching the existing default-off convention "
        "for pr_checks/dependabot/fork_prs"
    )


def test_js_test_runner_enum_maps_through_a_fixed_table_not_a_raw_policy_string() -> None:
    """Injection-safety structural proxy: the classifier must map the JS/TS
    runner enum value through a hardcoded table (e.g. a dict literal keyed on
    `off`/`vitest`/`jest`/`npm-test`/`pnpm-test`) rather than f-string-
    interpolating the raw policy value directly into the `js_install_cmd`/
    `js_test_grant` output lines — a free-form policy string reaching the
    agent allowlist would be an injection vector.
    """
    parsed = _parsed()
    job = _job(parsed, "classify")
    classify_step = _classify_step(job)
    assert classify_step is not None, "classify job must contain its `classify` step"
    run = classify_step.get("run") or ""
    assert re.search(r"vitest", run), "The classifier must contain a hardcoded 'vitest' table entry"
    assert not re.search(
        r'print\(f"js_(install_cmd|test_grant)=\{[^}]*provider\.get\("js_test_runner"', run
    ), (
        "js_install_cmd/js_test_grant must never be produced by directly "
        "f-string-interpolating the raw policy value — map it through a "
        "hardcoded table first"
    )


def test_install_js_deps_step_is_non_agent_and_uses_ignore_scripts() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_steps = [
        step
        for step in job.get("steps") or []
        if "install" in (step.get("name") or "").lower()
        and re.search(r"js|ts|npm|pnpm|node", step.get("name") or "", re.IGNORECASE)
    ]
    assert install_steps, (
        "autofix-same-repo-pr must contain a non-agent step installing "
        "JS/TS dependencies from the lockfile"
    )
    install_step = install_steps[0]
    assert "uses" not in install_step, "The JS/TS install step must be a non-agent `run:` step"
    assert "--ignore-scripts" in (
        install_step.get("run") or ""
    ), "The JS/TS install step must disable lifecycle scripts via --ignore-scripts"
    condition = install_step.get("if") or ""
    assert "js_test_grant" in condition, (
        "The JS/TS install step must be guarded on "
        "needs.classify.outputs.js_test_grant being non-empty"
    )
    assert (
        "steps.budget.outputs.proceed" in condition
    ), "The JS/TS install step must also be guarded on steps.budget.outputs.proceed == 'true'"


def test_fixer_allowlist_contains_no_install_command_for_js_test_runner() -> None:
    """Negative/absence invariant: the agent allowlist must never grant an
    install command, only a runner invocation. Expected GREEN on first run —
    there is no install command in today's allowlist to remove — and must
    stay GREEN once Bug B lands, since the design forbids granting install to
    the agent under any policy selection.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    allowed_tools = _claude_args(agent_steps[0])
    assert "npm ci" not in allowed_tools, "The fixer allowlist must never grant `npm ci`"
    assert "npm install" not in allowed_tools, "The fixer allowlist must never grant `npm install`"
    assert (
        "pnpm install" not in allowed_tools
    ), "The fixer allowlist must never grant `pnpm install`"


def test_allowedtools_value_stays_a_single_physical_line_after_js_test_grant_token_appended() -> (
    None
):
    """Bug B appends `${{ needs.classify.outputs.js_test_grant }}` as one
    more comma-separated token onto the SAME physical `--allowedTools` line
    tested generally above. Re-invoked here, scoped to the specific fixer
    step Bug B modifies, so a regression introduced while wiring the JS/TS
    grant token is caught at the exact site of the change — a source-text
    proxy only; the live dogfood confirms the rendered line.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    value = _allowed_tools_value(agent_steps[0])
    assert (
        value is not None
    ), 'Expected an --allowedTools "..." value in the fixer step\'s claude_args'
    assert "\n" not in value, (
        "The fixer step's --allowedTools value must stay a single physical "
        "line even after the JS/TS test-runner grant token is appended"
    )


def test_js_test_runner_off_leaves_the_same_repo_pr_allowlist_byte_identical_to_bug_a() -> None:
    """Structural proxy for the "runner off means byte-identical to Bug A"
    guarantee: the Bug-A-only baseline tokens (captured verbatim, pre-Bug-B)
    must remain the leading, unmodified prefix of
    `--allowedTools` — Bug B may only APPEND a templated JS/TS grant token
    after them, never rewrite or reorder the existing grant. When the
    selector is `off` (default), the appended template expression evaluates
    to an empty string and the rendered line becomes byte-identical to this
    baseline; that runtime evaluation is confirmed by the live dogfood, not
    by this structural test.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    value = _allowed_tools_value(agent_steps[0])
    assert (
        value is not None
    ), 'Expected an --allowedTools "..." value in the fixer step\'s claude_args'
    assert value.startswith(BUG_A_BASELINE_ALLOWED_TOOLS), (
        "The Bug-A-only baseline tokens must remain the leading, unmodified "
        "prefix of --allowedTools — Bug B may only append a templated JS/TS "
        "grant token after them"
    )
    assert "needs.classify.outputs.js_test_grant" in value, (
        "Bug B must template the JS/TS runner grant token from "
        "needs.classify.outputs.js_test_grant onto the allowlist — when the "
        "selector is off (default) this expression evaluates to an empty "
        "string, so the rendered line becomes byte-identical to the Bug-A "
        "baseline"
    )


# ---------------------------------------------------------------------------
# PM-aware install (autofix-pm-detect) — table split, detect_pm, robustness
#
# RED-phase note: today's classify step still derives js_install_cmd from the
# single coupled JS_RUNNER_TABLE keyed on js_test_runner alone — no lockfile
# detection exists. Assertions below that require actual PM detection are
# expected RED (a pnpm-lock.yaml fixture still yields "npm ci"). A handful are
# explicitly flagged as naturally-satisfied-today regression guards: today's
# code always falls back to "npm ci" regardless of any lockfile fixture, so
# scenarios whose CORRECT answer is also "npm ci" (no lockfile, only
# package-lock.json, or a lockfile sitting outside the declared project dir)
# already pass — they only start proving something once detect_pm lands.
# ---------------------------------------------------------------------------


def _classify_run_text(parsed: dict) -> str:
    """Return the classify job's `classify` step `run:` text (empty string
    if the step is absent — RED-safe)."""
    classify_step = _classify_step(_job(parsed, "classify"))
    return (classify_step.get("run") if classify_step else "") or ""


def _terms_co_occur(text: str, term_a: str, term_b: str, window: int = 60) -> bool:
    """True if the literal strings `term_a` and `term_b` co-occur within
    `window` chars of each other, either order."""
    pattern = re.compile(
        rf"({re.escape(term_a)}.{{0,{window}}}{re.escape(term_b)}|"
        rf"{re.escape(term_b)}.{{0,{window}}}{re.escape(term_a)})",
        re.DOTALL,
    )
    return bool(pattern.search(text))


def _extract_classify_script(run: str) -> str:
    """Extract the embedded Python heredoc body from the classify step's
    `run:` shell text (the part between `<<'PY'` and the closing `PY`)."""
    match = re.search(r"<<'PY'\n(.*?)\nPY\b", run, re.DOTALL)
    return match.group(1) if match else ""


def _run_classify_script(tmp_path: Path, *, policy: dict) -> dict[str, str]:
    """Execute the classify step's embedded Python script against `policy`,
    with `tmp_path` as its working directory — mirroring the real job, whose
    script runs against the already-checked-out default-branch tree rooted
    at the repo root.

    Any lockfile fixtures must already be seeded under `tmp_path` (optionally
    inside a project-dir-shaped subdirectory) before calling this.
    """
    source = _extract_classify_script(_classify_run_text(_parsed()))
    assert source, "Expected an embedded Python heredoc body in the classify step's run: text"
    script_path = tmp_path / "_classify_script.py"
    script_path.write_text(source, encoding="utf-8")
    policy_path = tmp_path / "autofix-policy.yml"
    policy_path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script_path), str(policy_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"classify script exited {result.returncode}; stderr:\n{result.stderr}"
    outputs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        outputs[key] = value
    return outputs


@pytest.mark.parametrize(
    ("pm", "expected_row"),
    [
        ("npm", "npm ci"),
        ("pnpm", "corepack enable && pnpm install --frozen-lockfile"),
        ("yarn", "corepack enable && yarn install --frozen-lockfile"),
    ],
)
def test_js_pm_install_row_ends_with_its_install_verb(pm: str, expected_row: str) -> None:
    """Each JS_PM_INSTALL row's value must end with its install verb, so the
    install step's appended ` --ignore-scripts` binds to the right command;
    pnpm/yarn rows are corepack-prefixed, npm's is not.
    """
    run = _classify_run_text(_parsed())
    assert re.search(rf'"{pm}":\s*"{re.escape(expected_row)}"', run), (
        f"Expected JS_PM_INSTALL[{pm!r}] == {expected_row!r} — install verb as "
        "the row's tail, decoupled from the js_test_runner enum"
    )


def test_js_runner_table_yields_runner_only_commands_decoupled_from_install() -> None:
    """After the split, JS_RUNNER_TABLE rows must be runner-only strings (no
    install half) — js_test_grant's vitest derivation must stay byte-identical
    to the pre-split baseline.
    """
    run = _classify_run_text(_parsed())
    assert re.search(r'"vitest":\s*"\./node_modules/\.bin/vitest run"', run), (
        "JS_RUNNER_TABLE['vitest'] must be the runner-only string "
        "'./node_modules/.bin/vitest run' (byte-identical to the pre-split "
        "baseline), not paired with an install command in a tuple"
    )
    assert not re.search(r'"vitest":\s*\(\s*"[^"]*"\s*,', run), (
        "JS_RUNNER_TABLE must no longer pair each runner with an install "
        "command in a tuple — the install half moves to JS_PM_INSTALL"
    )


def test_js_install_cmd_no_longer_derives_from_the_runner_enum_table() -> None:
    """Regression guard against re-coupling the two axes: js_install_cmd must
    no longer be unpacked from JS_RUNNER_TABLE — PM detection must drive it
    independently of the js_test_runner enum.
    """
    run = _classify_run_text(_parsed())
    assert not re.search(
        r"js_install_cmd\s*,\s*js_runner_cmd\s*=\s*JS_RUNNER_TABLE", run
    ), "js_install_cmd must no longer be unpacked from the coupled JS_RUNNER_TABLE tuple"


def test_js_install_cmd_is_selected_through_the_pm_install_table_not_interpolated() -> None:
    """Injection-safety idiom re-asserted for the new table: js_install_cmd
    must be selected via a closed-table lookup keyed on the detected package
    manager, never an f-string interpolating a value directly into it.
    """
    run = _classify_run_text(_parsed())
    assert "JS_PM_INSTALL[" in run or "JS_PM_INSTALL.get(" in run, (
        "js_install_cmd must be selected via a JS_PM_INSTALL[...] (or "
        ".get(...)) closed-table lookup, keyed on the detected package manager"
    )
    assert not re.search(r'js_install_cmd\s*=\s*f["\']', run), (
        "js_install_cmd must never be produced by f-string-interpolating a "
        "detected/raw value directly — select it through the closed "
        "JS_PM_INSTALL table instead"
    )


def test_detect_pm_is_invoked_with_the_declared_js_project_dir() -> None:
    """detect_pm must be called with js_project_dir as its argument — never a
    bare call with no directory scoping, which would probe the process's
    working directory (repo root) instead of the caller's JS/TS project dir.
    """
    run = _classify_run_text(_parsed())
    assert re.search(r"detect_pm\(\s*js_project_dir\s*\)", run), (
        "Expected a detect_pm(js_project_dir) call — passing the declared "
        "project dir so detection reads the right subdirectory, not repo root"
    )


@pytest.mark.parametrize("lockfile", ["pnpm-lock.yaml", "yarn.lock", "package-lock.json"])
def test_detect_pm_joins_each_lockfile_name_onto_a_directory_variable(lockfile: str) -> None:
    """Each lockfile-presence check must join the filename onto a directory
    variable (e.g. os.path.join(base, "pnpm-lock.yaml")) rather than testing
    a bare, process-CWD-relative literal — a bare check silently probes repo
    root instead of the caller's JS/TS project directory.
    """
    run = _classify_run_text(_parsed())
    assert lockfile in run, f"Expected a {lockfile!r} presence check driving PM detection"
    assert _terms_co_occur(run, "os.path.join(", lockfile, window=60), (
        f"The {lockfile!r} presence check must join the filename onto a "
        "directory variable via os.path.join — a bare literal check would "
        "silently probe the process's working directory (repo root)"
    )


def test_detect_pm_checks_lockfiles_in_pnpm_yarn_npm_precedence_order() -> None:
    """Fixed precedence keeps detection deterministic if a stale second
    lockfile ever reappears alongside the real one.
    """
    run = _classify_run_text(_parsed())
    pnpm_pos = run.find("pnpm-lock.yaml")
    yarn_pos = run.find("yarn.lock")
    npm_pos = run.find("package-lock.json")
    assert pnpm_pos != -1, "Expected a pnpm-lock.yaml presence check"
    assert yarn_pos != -1, "Expected a yarn.lock presence check"
    assert npm_pos != -1, "Expected a package-lock.json presence check"
    assert pnpm_pos < yarn_pos, "pnpm-lock.yaml must be checked before yarn.lock (pnpm > yarn)"
    assert yarn_pos < npm_pos, "yarn.lock must be checked before package-lock.json (yarn > npm)"


def test_pnpm_lockfile_under_the_project_dir_selects_a_pnpm_install(tmp_path: Path) -> None:
    """The highest-value regression guard: detection must probe under the
    caller's js_project_dir, not the process's working directory (repo
    root) — Praxion's own repo root carries no lockfile at all, so a
    root-scoped probe would silently fall back to npm and reproduce the
    original #48 defect.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    (project_dir / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "pnpm install" in outputs.get("js_install_cmd", ""), (
        "Expected a pnpm install command for a pnpm-lock.yaml found under "
        f"js_project_dir; got js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_yarn_lockfile_under_the_project_dir_selects_a_yarn_install(tmp_path: Path) -> None:
    """When no pnpm-lock.yaml is present but yarn.lock is, detection must
    select the yarn install row.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    (project_dir / "yarn.lock").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "yarn install" in outputs.get(
        "js_install_cmd", ""
    ), f"Expected a yarn install command; got js_install_cmd={outputs.get('js_install_cmd')!r}"


def test_package_lock_json_under_the_project_dir_selects_npm_ci(tmp_path: Path) -> None:
    """Naturally satisfied today (npm ci is the universal current fallback,
    regardless of any lockfile) — becomes a real regression guard once
    detect_pm's per-PM branching lands: package-lock.json alone must still
    resolve to npm ci, not silently drift to another package manager.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    (project_dir / "package-lock.json").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert (
        "npm ci" in outputs.get("js_install_cmd", "")
    ), f"Expected npm ci as the install command; got js_install_cmd={outputs.get('js_install_cmd')!r}"


def test_pnpm_lockfile_takes_precedence_over_a_stale_package_lock_json(tmp_path: Path) -> None:
    """Defense-in-depth: fixed precedence (pnpm > yarn > npm) keeps detection
    correct even if a stale second lockfile lingers alongside the real one —
    exactly Praxion's own dashboard_app/ situation pre-cleanup.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    (project_dir / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "pnpm install" in outputs.get("js_install_cmd", ""), (
        "Expected pnpm to win over a stale package-lock.json; got "
        f"js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_no_lockfile_under_the_project_dir_falls_back_to_npm_ci(tmp_path: Path) -> None:
    """Naturally satisfied today (npm ci is the universal current fallback);
    becomes a real regression guard once detect_pm lands, proving its
    fail-safe default still resolves to npm ci rather than raising or
    silently emitting an empty command.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "npm ci" in outputs.get("js_install_cmd", ""), (
        "Expected npm ci as the fail-safe default when no lockfile is present; "
        f"got js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_a_pnpm_lockfile_at_repo_root_is_ignored_when_js_project_dir_points_elsewhere(
    tmp_path: Path,
) -> None:
    """Directly closes the highest-likelihood regression: a lockfile sitting
    at repo root must NOT satisfy detection when js_project_dir points
    elsewhere — detection must probe the declared project dir, never
    wherever the classify job's working directory happens to be. Naturally
    satisfied today (npm ci is the universal current fallback); becomes the
    load-bearing regression guard once detect_pm lands.
    """
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "npm ci" in outputs.get("js_install_cmd", ""), (
        "A repo-root lockfile must not be detected when js_project_dir points "
        f"elsewhere; got js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_js_install_cmd_stays_empty_when_the_runner_is_off_even_with_a_lockfile_present(
    tmp_path: Path,
) -> None:
    """Closes the surface-widening invariant: a repo with any lockfile but
    js_test_runner: off must never receive an install command — the
    JS_PM_INSTALL lookup must stay gated on a granted runner, not on
    lockfile presence alone. Naturally satisfied today (the coupled table's
    "off" row already pairs an empty install with an empty runner); becomes
    the regression guard proving the split didn't drop this gate.
    """
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "off"}},
    )
    assert outputs.get("js_install_cmd", "") == "", (
        "js_install_cmd must stay empty when js_test_runner is off, "
        f"regardless of lockfile presence; got {outputs.get('js_install_cmd')!r}"
    )


# ---------------------------------------------------------------------------
# Install-step robustness + fixer gate (autofix-pm-detect)
#
# RED-phase note: today's install step has no `id`, no `continue-on-error`,
# and no env block; the fixer step's `if` has no install-outcome clause.
# Two assertions are explicitly flagged as preventive regression guards
# (already true today, must stay true after the change): the install step
# already ends in --ignore-scripts, and the fixer's if already requires the
# budget-proceed flag.
# ---------------------------------------------------------------------------


def _install_step(job: dict) -> dict | None:
    """Return the JS/TS install step in a job, or `None` if absent (RED-safe)."""
    for step in job.get("steps") or []:
        name = (step.get("name") or "").lower()
        if "install" in name and re.search(r"js|ts|npm|pnpm|node", name, re.IGNORECASE):
            return step
    return None


def test_install_step_declares_an_addressable_id_for_the_fixer_gate() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_step = _install_step(job)
    assert install_step is not None, "autofix-same-repo-pr must contain a JS/TS install step"
    assert install_step.get("id") == "js_install", (
        "The install step must declare `id: js_install` so the fixer step's "
        "gate can address its outcome"
    )


def test_install_step_is_continue_on_error_so_a_failure_does_not_fail_the_job() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_step = _install_step(job)
    assert install_step is not None, "autofix-same-repo-pr must contain a JS/TS install step"
    assert install_step.get("continue-on-error") is True, (
        "The install step must carry `continue-on-error: true` so a failed "
        "install degrades the run to a green decline instead of a red job"
    )


def test_install_step_disables_the_corepack_interactive_download_prompt() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_step = _install_step(job)
    assert install_step is not None, "autofix-same-repo-pr must contain a JS/TS install step"
    env = install_step.get("env") or {}
    assert str(env.get("COREPACK_ENABLE_DOWNLOAD_PROMPT")) == "0", (
        "The install step's env must set COREPACK_ENABLE_DOWNLOAD_PROMPT=0 so "
        "corepack's first-use provisioning never blocks on an interactive "
        "prompt in non-TTY CI"
    )


def test_install_step_still_appends_ignore_scripts_after_the_corepack_prefix() -> None:
    """Regression guard, naturally satisfied today: the corepack provisioning
    prefix must not disturb the pre-existing --ignore-scripts flag the
    install step always appends.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_step = _install_step(job)
    assert install_step is not None, "autofix-same-repo-pr must contain a JS/TS install step"
    run = install_step.get("run") or ""
    assert run.rstrip().endswith(
        "--ignore-scripts"
    ), "The install step's run line must still end in --ignore-scripts"


def test_no_new_third_party_action_provisions_pnpm_or_yarn() -> None:
    """Regression guard, naturally satisfied today (neither reference exists
    yet): pnpm/yarn are provisioned via the runner's bundled corepack, not a
    new SHA-pinned uses: action — a privileged CI surface should not grow
    its supply-chain footprint to fix an install-detection bug.
    """
    parsed = _parsed()
    refs = _uses_refs(parsed)
    assert not any(
        "pnpm/action-setup" in ref for ref in refs
    ), "No pnpm/action-setup reference is expected — pnpm is provisioned via corepack"
    assert not any("actions/setup-node" in ref for ref in refs), (
        "No actions/setup-node reference is expected — Node ships pre-installed "
        "on the runner; only corepack enable is needed"
    )


def test_fixer_step_is_gated_on_the_install_step_not_having_failed() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    condition = agent_steps[0].get("if") or ""
    assert "steps.js_install.outcome != 'failure'" in condition, (
        "The fixer step's `if:` must skip when the install step's outcome is "
        "'failure', so the fixer never thrashes against a missing node_modules"
    )


def test_fixer_gate_still_requires_the_budget_proceed_flag() -> None:
    """Regression guard, naturally satisfied today: the new install-outcome
    clause must be additive — the pre-existing budget-proceed gate must
    still hold alongside it, never be replaced by it.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    condition = agent_steps[0].get("if") or ""
    assert "steps.budget.outputs.proceed == 'true'" in condition, (
        "The fixer step's `if:` must still require "
        "steps.budget.outputs.proceed == 'true' alongside the new "
        "install-outcome gate"
    )
