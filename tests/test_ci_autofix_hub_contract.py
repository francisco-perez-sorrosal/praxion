"""Structural invariants for the ci-autofix hub's file-wide contract.

Covers `.github/workflows/reusable-ci-autofix.yml` as a whole: its
`workflow_call` interface, the carried-over P0 banned patterns, supply-chain
pinning, the layered loop-prevention gates, sanitized-logs-as-data, the
sensitive-path tripwire, plugin-dir generalization, fail-safe policy defaults,
top-level concurrency scoping, and the byte-stability anchor pinning the
original main-branch `autofix` job's shape.

Invariants here are scoped to the workflow as a unit — every job, every step —
rather than to any one surface job. Per-surface contracts live in the siblings.

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


def _claude_args(step: dict) -> str:
    """Return a claude-code-action step's `with.claude_args` block (the `--allowedTools` carrier)."""
    return (step.get("with") or {}).get("claude_args", "") or ""


def _all_agent_steps(parsed: dict) -> list[dict]:
    """Return every `claude-code-action` step across every job in the workflow."""
    return [step for step in _all_steps(parsed) if "claude-code-action" in (step.get("uses") or "")]


def _allowed_tools_value(step: dict) -> str | None:
    """Extract the quoted value of `--allowedTools "..."` from a step's `claude_args`."""
    match = re.search(r'--allowedTools "([^"]*)"', _claude_args(step))
    return match.group(1) if match else None


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
    assert inputs["policy_path"].get("default") == ".github/autofix-policy.yml", (
        "`policy_path` input must default to '.github/autofix-policy.yml'"
    )


def test_workflow_call_declares_required_oauth_secret() -> None:
    parsed = _parsed()
    workflow_call = _on_block(parsed)["workflow_call"]
    secrets_block = workflow_call.get("secrets", {}) or {}
    assert "CLAUDE_CODE_OAUTH_TOKEN" in secrets_block, (
        "on.workflow_call.secrets must declare CLAUDE_CODE_OAUTH_TOKEN"
    )
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
    assert "pull_request_target" not in raw, (
        "`pull_request_target` must never appear anywhere in the hub"
    )


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
    assert any("conclusion" in c and "failure" in c for c in conditions), (
        "At least one job must gate on the failed run's `conclusion == 'failure'`"
    )


def test_branch_gate_uses_default_branch_not_hardcoded_main() -> None:
    raw = _raw_text()
    assert "default_branch" in raw, (
        "The branch gate must reference github.event.repository.default_branch — "
        "generalizing the shipped workflow's hardcoded 'main' so the hub works on "
        "managed repos whose default branch is not 'main'"
    )
    assert not re.search(r"head_branch\s*==\s*['\"]main['\"]", raw), (
        "The branch gate must not hardcode `head_branch == 'main'`"
    )


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
    assert _policy_read_step(parsed) is not None, (
        "Hub must contain a non-agent step that reads/parses the caller's autofix-policy.yml"
    )


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
    assert "head_branch == github.event.repository.default_branch" in condition, (
        "The `autofix` job's branch gate must remain unchanged"
    )
    assert autofix_job.get("permissions", {}).get("contents") == "write", (
        "The `autofix` job's `contents: write` grant must remain unchanged"
    )
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
# Allowlist single-line invariant (whole-workflow scope)
# ---------------------------------------------------------------------------


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
        assert value is not None, (
            f'Expected an --allowedTools "..." value in {step.get("name")!r}\'s claude_args'
        )
        assert "\n" not in value, (
            f"{step.get('name')!r}'s --allowedTools value must stay a single "
            "physical line — a wrapped allowlist is silently narrowed at runtime"
        )
