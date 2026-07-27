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
from pathlib import Path

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
    assert step_names == [
        "Checkout caller repo's default branch",
        "Set up uv (manages Python 3.13)",
        "Read autofix policy (fail-safe defaults)",
        "Enforce daily run budget",
        "Skip if an autofix PR is already open",
        "Fetch failure logs (non-agent, untrusted output)",
        "Diagnose failure and open a fix PR",
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
