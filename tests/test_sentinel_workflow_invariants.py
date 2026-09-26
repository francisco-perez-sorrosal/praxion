"""Structural invariant tests for the scheduled sentinel workflow.

These tests define the security envelope `.github/workflows/sentinel.yml`
must satisfy when building the weekly (plus
on-demand) run of the read-only ecosystem-quality auditor against `main`, with
a public-repo artifact as its only externally visible output. Every test reads
the file lazily (inside the function body, not at module import time), so a
missing workflow fails the tests rather than their collection.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps, permission grants, and banned patterns. It cannot
verify runtime behavior (whether the pinned action's agent mode truly honours
`--agent` as documented, whether `--settings` truly outranks the committed
project settings for a given key, whether `--strict-mcp-config` truly keeps
plugin MCP servers from starting) — those guarantees close only via a live
dispatch in production CI.

Modeled directly on the shipped sibling covering the issue-autofix fixer
workflow — lazy file read, `_on_block`/`_jobs`/`_all_steps`/`_uses_refs`
helper reuse, and the `--claude_args`-string-parsing helper for
`claude-code-action` steps.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "sentinel.yml"
SENTINEL_AGENT_FILE = PROJECT_ROOT / "agents" / "sentinel.md"

SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# The exact commits the sibling autofix/audit workflows already pin — this
# workflow must match them character-for-character, never re-resolve to a
# newer/older SHA of its own.
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"  # actions/checkout v7.0.1
SETUP_UV_SHA = "c771a70e6277c0a99b617c7a806ffedaca235ff9"  # astral-sh/setup-uv v9.0.0
CLAUDE_CODE_ACTION_SHA = (
    "51ea8ea73a139f2a74ff649e3092c25a904aed7e"  # anthropics/claude-code-action v1
)

# Permission keys that must never appear on any permissions block anywhere in
# this workflow — `contents` is checked separately because `contents: read`
# is the one permission the job legitimately holds.
FORBIDDEN_PERMISSION_KEYS = {"id-token", "pull-requests", "issues", "actions"}

# The ten kill-switch env flags the `--settings` payload must force to "1" so
# the sentinel's own scheduled session never writes an observation WAL, posts
# events, or trips an install/heal/injection side effect meant for a real
# interactive session.
KILL_SWITCH_FLAGS = (
    "PRAXION_DISABLE_OBSERVABILITY",
    "PRAXION_DISABLE_EVENT_POSTING",
    "PRAXION_DISABLE_AUTO_COMPLETE",
    "PRAXION_DISABLE_HOOK_CHAIN_HEAL",
    "PRAXION_DISABLE_RULE_INJECTION",
    "PRAXION_DISABLE_DECISION_INJECTION",
    "PRAXION_DISABLE_PROCESS_INJECT",
    "PRAXION_DISABLE_FEEDBACK_SURFACING",
    "PRAXION_DISABLE_SIDECAR_BANNER",
    "PRAXION_DISABLE_SIDECAR_AUTOCOMMIT",
)


# ---------------------------------------------------------------------------
# Helpers — parsing
# ---------------------------------------------------------------------------


def _raw_text() -> str:
    """Return the workflow's raw file content (read lazily so collection succeeds)."""
    return WORKFLOW_FILE.read_text(encoding="utf-8")


def _parsed() -> dict:
    """Parse the workflow as YAML."""
    return yaml.safe_load(_raw_text())


def _on_block(parsed: dict) -> dict:
    """Return the `on:` trigger block.

    PyYAML's default (YAML 1.1) resolver treats the bare scalar `on` as the
    boolean `True` — including when it appears as a mapping key — so a
    top-level `on:` block parses under the key `True`, not the string `"on"`.
    """
    if "on" in parsed:
        return parsed["on"]
    if True in parsed:
        return parsed[True]
    raise AssertionError("Workflow has no `on:` trigger block")


def _jobs(parsed: dict) -> dict:
    """Return the workflow's `jobs:` mapping."""
    return parsed.get("jobs") or {}


def _all_steps(parsed: dict) -> list[dict]:
    """Flatten every step across every job in the workflow."""
    steps: list[dict] = []
    for job in _jobs(parsed).values():
        steps.extend(job.get("steps") or [])
    return steps


def _uses_refs(parsed: dict) -> list[str]:
    """Collect every `uses:` value across every job/step in the workflow."""
    return [step["uses"] for step in _all_steps(parsed) if step.get("uses")]


def _job_permissions(parsed: dict) -> list[dict]:
    """Return every job's own `permissions:` mapping (empty dict if a job omits it)."""
    return [job.get("permissions") or {} for job in _jobs(parsed).values()]


def _claude_args_blocks(parsed: dict) -> list[str]:
    """Return every `with.claude_args` string across all `claude-code-action` steps."""
    return [
        (step.get("with") or {}).get("claude_args", "")
        for step in _all_steps(parsed)
        if "claude-code-action" in (step.get("uses") or "")
    ]


def _action_steps(parsed: dict) -> list[dict]:
    """Return every `claude-code-action` step in the workflow."""
    return [step for step in _all_steps(parsed) if "claude-code-action" in (step.get("uses") or "")]


def _sentinel_tool_grant() -> set[str]:
    """Parse `tools:` from `agents/sentinel.md`'s frontmatter.

    This is the paired-site ceiling: the workflow's `--allowedTools` must never
    grant more than the interactive agent's own tool grant. Reading the real
    frontmatter (rather than hardcoding a duplicate list) means this check
    tracks the agent's actual grant if it ever changes.
    """
    text = SENTINEL_AGENT_FILE.read_text(encoding="utf-8")
    match = re.search(r"^tools:\s*(.+)$", text, re.MULTILINE)
    assert match, "agents/sentinel.md frontmatter must declare a `tools:` line"
    return {t.strip() for t in match.group(1).split(",") if t.strip()}


def _settings_json(parsed: dict) -> dict:
    """Parse the `--settings '<json>'` payload out of `claude_args`."""
    combined = " ".join(_claude_args_blocks(parsed))
    match = re.search(r"--settings\s+'(\{.*?\})'", combined, re.DOTALL)
    assert match, "`claude_args` must declare `--settings '<json>'`"
    return json.loads(match.group(1))


# ---------------------------------------------------------------------------
# Helpers — predicates (shared between the direct invariant tests and the
# mutation canaries below; a predicate that only ever runs against the real,
# correct file can't prove it would catch a wrong one)
# ---------------------------------------------------------------------------


def _assert_triggers_exact(parsed: dict) -> None:
    on_block = _on_block(parsed)
    assert set(on_block) == {"schedule", "workflow_dispatch"}, (
        f"Workflow `on:` must declare exactly {{schedule, workflow_dispatch}} — "
        f"got {set(on_block)}. Any other trigger (e.g. a PR-context event) would "
        "run this secret-bearing, unrestricted-Bash job against untrusted content."
    )


def _assert_workflow_permissions_are_empty(parsed: dict) -> None:
    assert parsed.get("permissions") == {}, (
        "Workflow-level `permissions:` must be the empty mapping `{}` — the "
        "least-privilege floor every job re-grants from, never inherits above"
    )


def _assert_job_permissions_are_exactly_contents_read(parsed: dict) -> None:
    permissions = _job_permissions(parsed)
    assert permissions, "Workflow must declare at least one job with its own `permissions:`"
    assert all(perm == {"contents": "read"} for perm in permissions), (
        f"Every job's own `permissions:` must be EXACTLY {{'contents': 'read'}} — got {permissions}"
    )


def _assert_no_permission_block_grants_forbidden_keys(parsed: dict) -> None:
    all_perms = [parsed.get("permissions") or {}, *_job_permissions(parsed)]
    for perm in all_perms:
        offending = set(perm) & FORBIDDEN_PERMISSION_KEYS
        assert not offending, (
            f"Permission block {perm} grants forbidden key(s) {offending} — this "
            "job may never hold id-token, pull-requests, issues, or actions"
        )
        assert perm.get("contents") != "write", (
            f"Permission block {perm} grants `contents: write` — this job is "
            "read-only end to end, it must never hold write access to the repo"
        )


def _assert_github_token_present_on_action_step(parsed: dict) -> None:
    action_steps = _action_steps(parsed)
    assert action_steps, "Expected a claude-code-action step"
    for step in action_steps:
        with_block = step.get("with") or {}
        assert with_block.get("github_token"), (
            "The claude-code-action step must supply `github_token:` — without "
            "it, the pinned action requests an OIDC token and exchanges it for "
            "a Claude-App installation token whose default permissions "
            "(contents/pull_requests/issues: write) are not bounded by the "
            "job's own `permissions:` block at all"
        )


def _assert_allowed_tools_subset_of_sentinel_grant(parsed: dict) -> None:
    claude_args_blocks = _claude_args_blocks(parsed)
    assert claude_args_blocks, "Expected a claude-code-action step with claude_args"
    allowed_grant = _sentinel_tool_grant()
    for block in claude_args_blocks:
        match = re.search(r'--allowedTools\s+"([^"]*)"', block)
        assert match, "`claude_args` must declare `--allowedTools`"
        tools = {t.strip() for t in match.group(1).split(",") if t.strip()}
        extra = tools - allowed_grant
        assert not extra, (
            f"`--allowedTools` grants {extra} beyond agents/sentinel.md's own "
            f"tool grant {allowed_grant} — the scheduled job's tool grant must "
            "be no wider than the interactive agent's"
        )


# ---------------------------------------------------------------------------
# Helpers — mutators for the mutation canaries
# ---------------------------------------------------------------------------


def _mutate_add_pull_request_trigger(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    _on_block(mutated)["pull_request"] = {}
    return mutated


def _mutate_add_contents_write_permission(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for job in _jobs(mutated).values():
        job.setdefault("permissions", {})["contents"] = "write"
    return mutated


def _mutate_add_id_token_permission(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for job in _jobs(mutated).values():
        job.setdefault("permissions", {})["id-token"] = "write"
    return mutated


def _mutate_drop_github_token(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _action_steps(mutated):
        (step.get("with") or {}).pop("github_token", None)
    return mutated


def _mutate_widen_allowed_tools_beyond_grant(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _action_steps(mutated):
        with_block = step.get("with") or {}
        args = with_block.get("claude_args", "")
        match = re.search(r'(--allowedTools\s+")([^"]*)(")', args)
        if not match:
            continue
        prefix, tools, suffix = match.groups()
        with_block["claude_args"] = (
            args[: match.start()] + prefix + tools + ",Edit" + suffix + args[match.end() :]
        )
    return mutated


# ---------------------------------------------------------------------------
# Existence and parseability
# ---------------------------------------------------------------------------


def test_workflow_file_exists_and_parses_as_yaml() -> None:
    assert WORKFLOW_FILE.exists(), (
        f"{WORKFLOW_FILE} not found. The writer must create the scheduled sentinel workflow."
    )
    parsed = _parsed()
    assert isinstance(parsed, dict), "Workflow must parse to a YAML mapping"


# ---------------------------------------------------------------------------
# (a) Trigger contract — schedule + workflow_dispatch only
# ---------------------------------------------------------------------------


def test_triggers_are_exactly_schedule_and_workflow_dispatch() -> None:
    _assert_triggers_exact(_parsed())


def test_schedule_cron_fires_monday_mornings() -> None:
    parsed = _parsed()
    schedule_entries = _on_block(parsed).get("schedule") or []
    crons = [entry.get("cron") for entry in schedule_entries if isinstance(entry, dict)]
    assert "0 7 * * 1" in crons, (
        f"`on.schedule` must include the cron `0 7 * * 1` (Mondays 07:00 UTC) — got {crons}"
    )


# ---------------------------------------------------------------------------
# (b), (c) Least privilege — workflow floor empty, job exactly contents:read,
# no permission block anywhere grants a forbidden key
# ---------------------------------------------------------------------------


def test_workflow_permissions_are_empty() -> None:
    _assert_workflow_permissions_are_empty(_parsed())


def test_job_permissions_are_exactly_contents_read() -> None:
    _assert_job_permissions_are_exactly_contents_read(_parsed())


def test_no_permission_block_grants_a_forbidden_key() -> None:
    _assert_no_permission_block_grants_forbidden_keys(_parsed())


# ---------------------------------------------------------------------------
# (d) Supply-chain pinning
# ---------------------------------------------------------------------------


def test_every_uses_reference_is_sha_pinned_with_a_version_comment() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    assert refs, "Workflow must contain at least one `uses:` step"
    for ref in refs:
        assert "@" in ref, f"`uses: {ref}` must pin a ref via '@<sha>'"
        pinned_ref = ref.rsplit("@", 1)[1]
        assert SHA_PIN_PATTERN.match(pinned_ref), (
            f"`uses: {ref}` must be pinned to a full 40-hex commit SHA, not a "
            f"mutable tag or branch (got {pinned_ref!r})"
        )

    uses_lines = [
        line for line in _raw_text().splitlines() if re.search(r"uses:\s*\S+@[0-9a-f]{40}", line)
    ]
    assert uses_lines, "Expected at least one `uses:` line pinned to a SHA"
    for line in uses_lines:
        assert re.search(r"#\s*v\d", line), (
            f"`uses:` line {line.strip()!r} must carry a trailing version comment (e.g. `# v1.0.0`)"
        )


def test_claude_code_action_pin_matches_the_autofix_workflows_pin() -> None:
    refs = _uses_refs(_parsed())
    matching = [ref for ref in refs if ref.startswith("anthropics/claude-code-action@")]
    assert matching, "Expected an `anthropics/claude-code-action` step"
    assert any(
        ref == f"anthropics/claude-code-action@{CLAUDE_CODE_ACTION_SHA}" for ref in matching
    ), (
        f"anthropics/claude-code-action must pin to the same commit already used "
        f"by the autofix workflows, {CLAUDE_CODE_ACTION_SHA} (got {matching})"
    )


def test_checkout_pin_matches_the_scheduled_audits_pin() -> None:
    refs = _uses_refs(_parsed())
    matching = [ref for ref in refs if ref.startswith("actions/checkout@")]
    assert matching, "Expected an `actions/checkout` step"
    assert any(ref == f"actions/checkout@{CHECKOUT_SHA}" for ref in matching), (
        f"actions/checkout must pin to the same commit already used by the "
        f"scheduled-audits workflow, {CHECKOUT_SHA} (got {matching})"
    )


def test_setup_uv_pin_matches_the_scheduled_audits_pin() -> None:
    refs = _uses_refs(_parsed())
    matching = [ref for ref in refs if ref.startswith("astral-sh/setup-uv@")]
    assert matching, "Expected an `astral-sh/setup-uv` step"
    assert any(ref == f"astral-sh/setup-uv@{SETUP_UV_SHA}" for ref in matching), (
        f"astral-sh/setup-uv must pin to the same commit already used by the "
        f"scheduled-audits workflow, {SETUP_UV_SHA} (got {matching})"
    )


# ---------------------------------------------------------------------------
# (e) Secret hygiene — exactly one reference, on the action step's with:
# ---------------------------------------------------------------------------


def test_oauth_secret_is_referenced_exactly_once_on_the_action_steps_with_block() -> None:
    raw = _raw_text()
    occurrences = raw.count("secrets.CLAUDE_CODE_OAUTH_TOKEN")
    assert occurrences == 1, (
        f"`secrets.CLAUDE_CODE_OAUTH_TOKEN` must appear exactly once in the whole "
        f"file — found {occurrences}"
    )
    action_steps = _action_steps(_parsed())
    assert action_steps, "Expected a claude-code-action step"
    with_values = " ".join(str(v) for v in (action_steps[0].get("with") or {}).values())
    assert "secrets.CLAUDE_CODE_OAUTH_TOKEN" in with_values, (
        "The oauth secret reference must live on the claude-code-action step's `with:` block"
    )


def test_no_env_block_carries_the_secret() -> None:
    parsed = _parsed()
    envs = [parsed.get("env") or {}]
    for job in _jobs(parsed).values():
        envs.append(job.get("env") or {})
    for step in _all_steps(parsed):
        envs.append(step.get("env") or {})
    for env in envs:
        combined = " ".join(str(v) for v in env.values())
        assert "secrets." not in combined, (
            f"No `env:` block may carry a `secrets.` reference — the oauth token "
            f"must reach the action only via its `with:` input, never a workflow-, "
            f"job-, or step-level env var (got {env})"
        )


# ---------------------------------------------------------------------------
# (f) github_token present on the action step
# ---------------------------------------------------------------------------


def test_github_token_is_present_on_the_action_step() -> None:
    _assert_github_token_present_on_action_step(_parsed())


# ---------------------------------------------------------------------------
# (g) claude_args — plugin, agent, turn cap, model, MCP strictness, tool grant
# ---------------------------------------------------------------------------


def test_claude_args_declares_plugin_dir_and_the_qualified_agent() -> None:
    combined = " ".join(_claude_args_blocks(_parsed()))
    assert "--plugin-dir ." in combined, "`claude_args` must declare `--plugin-dir .`"
    assert "--agent praxion:sentinel" in combined, (
        "`claude_args` must declare the fully-qualified `--agent praxion:sentinel` "
        "— an unprefixed plugin-agent lookup is not guaranteed at every CLI version"
    )


def test_claude_args_max_turns_is_at_most_150() -> None:
    combined = " ".join(_claude_args_blocks(_parsed()))
    match = re.search(r"--max-turns\s+(\d+)", combined)
    assert match, "`claude_args` must declare `--max-turns N`"
    assert int(match.group(1)) <= 150, (
        f"`--max-turns` must be at most 150 (got {match.group(1)}) — the cost-"
        "bounding cap this job runs under"
    )


def test_claude_args_model_names_a_sonnet_variant() -> None:
    combined = " ".join(_claude_args_blocks(_parsed()))
    match = re.search(r"--model\s+(\S+)", combined)
    assert match, "`claude_args` must declare an explicit `--model`"
    assert "sonnet" in match.group(1).lower(), (
        f"`--model` must name a sonnet variant (got {match.group(1)!r}) so a "
        "silent alias move never changes this job's cost profile unnoticed"
    )


def test_claude_args_declares_strict_mcp_config() -> None:
    combined = " ".join(_claude_args_blocks(_parsed()))
    assert "--strict-mcp-config" in combined, (
        "`claude_args` must declare `--strict-mcp-config` so plugin MCP servers "
        "never start in this unattended CI session"
    )


def test_claude_args_disallows_edit() -> None:
    combined = " ".join(_claude_args_blocks(_parsed()))
    match = re.search(r'--disallowedTools\s+"([^"]*)"', combined)
    assert match, "`claude_args` must declare `--disallowedTools`"
    assert "Edit" in {t.strip() for t in match.group(1).split(",")}, (
        "`--disallowedTools` must contain `Edit` — the sentinel is read-only, "
        "it observes and never fixes"
    )


def test_allowed_tools_is_a_subset_of_the_sentinel_agents_own_grant() -> None:
    _assert_allowed_tools_subset_of_sentinel_grant(_parsed())


# ---------------------------------------------------------------------------
# (h) Kill-switch settings
# ---------------------------------------------------------------------------


def test_settings_json_parses_and_forces_every_kill_switch_to_one() -> None:
    settings = _settings_json(_parsed())
    env = settings.get("env") or {}
    for flag in KILL_SWITCH_FLAGS:
        assert env.get(flag) == "1", (
            f'`--settings` env must set {flag} to "1" — every kill-switch flag '
            "must be forced on so the sentinel's own scheduled session never "
            "writes an observation WAL, posts events, or triggers an "
            "install/heal/injection side effect meant for a real interactive session"
        )


# ---------------------------------------------------------------------------
# (i) Subprocess env scrub on the agent step
# ---------------------------------------------------------------------------


def test_env_scrub_is_set_on_the_agent_step() -> None:
    action_steps = _action_steps(_parsed())
    assert action_steps, "Expected a claude-code-action step"
    for step in action_steps:
        env = step.get("env") or {}
        assert env.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") == "1", (
            'The agent step must set `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"` so '
            "Anthropic credentials are stripped from the environments of any "
            "Bash, hook, or stdio-MCP subprocess the agent spawns"
        )


# ---------------------------------------------------------------------------
# (j) Checkout never persists credentials
# ---------------------------------------------------------------------------


def test_checkout_step_disables_persisted_credentials() -> None:
    checkout_steps = [
        step
        for step in _all_steps(_parsed())
        if (step.get("uses") or "").startswith("actions/checkout@")
    ]
    assert checkout_steps, "Expected an actions/checkout step"
    for step in checkout_steps:
        with_block = step.get("with") or {}
        assert with_block.get("persist-credentials") is False, (
            "`actions/checkout` must set `persist-credentials: false` — the "
            "pinned action's agent mode still rewrites the remote URL with the "
            "contents: read job token, but checkout must not add a second copy"
        )


# ---------------------------------------------------------------------------
# (k) No push or commit anywhere
# ---------------------------------------------------------------------------


def test_no_run_step_pushes_or_commits() -> None:
    for step in _all_steps(_parsed()):
        run = step.get("run") or ""
        assert not re.search(r"\bgit push\b", run), (
            f"`run:` step must never call `git push` — found in {run!r}"
        )
        assert not re.search(r"\bgit commit\b", run), (
            f"`run:` step must never call `git commit` — found in {run!r}"
        )


# ---------------------------------------------------------------------------
# (l) Verify → gate → publish ordering
# ---------------------------------------------------------------------------


def test_report_check_step_runs_always_and_has_an_exit_path() -> None:
    steps = _all_steps(_parsed())
    report_check_steps = [
        step
        for step in steps
        if re.search(r"report", (step.get("name") or "") + (step.get("run") or ""), re.IGNORECASE)
        and "exit 1" in (step.get("run") or "")
    ]
    assert report_check_steps, (
        "A report-check step must exist with an `exit 1` path — it fires when "
        "no new report was produced"
    )
    for step in report_check_steps:
        assert step.get("if") == "always()", (
            "The report-check step must be `if: always()` so it still runs even "
            "when the (continue-on-error) agent step failed, timed out, or crashed"
        )


def test_credential_gate_precedes_the_upload_step() -> None:
    steps = _all_steps(_parsed())
    gate_idx: int | None = None
    upload_idx: int | None = None
    for idx, step in enumerate(steps):
        run = step.get("run") or ""
        uses = step.get("uses") or ""
        if gate_idx is None and re.search(r"sk-ant-|gh[opsru]_", run):
            gate_idx = idx
        if upload_idx is None and "upload-artifact" in uses:
            upload_idx = idx
    assert gate_idx is not None, (
        "A credential-gate step must exist, grepping for token-shaped patterns"
    )
    assert upload_idx is not None, "Expected an `actions/upload-artifact` step"
    assert gate_idx < upload_idx, (
        "The credential gate must run BEFORE the upload step — a report or "
        "patch that matches a token pattern must fail the job before anything "
        "reaches the public artifact"
    )


# ---------------------------------------------------------------------------
# (m) Timeouts
# ---------------------------------------------------------------------------


def test_job_and_agent_step_both_declare_timeouts() -> None:
    parsed = _parsed()
    jobs = _jobs(parsed)
    assert jobs, "Workflow must declare at least one job"
    for job in jobs.values():
        assert job.get("timeout-minutes"), "Job must declare `timeout-minutes:`"
    action_steps = _action_steps(parsed)
    assert action_steps, "Expected a claude-code-action step"
    for step in action_steps:
        assert step.get("timeout-minutes"), (
            "The agent step must declare its own `timeout-minutes:`, tighter "
            "than the job-level ceiling, so a hung Bash subprocess doesn't "
            "silently burn the whole job budget"
        )


# ---------------------------------------------------------------------------
# (n) No track_progress (the tool-scope-leak regression)
# ---------------------------------------------------------------------------


def test_never_references_track_progress() -> None:
    assert "track_progress" not in _raw_text(), (
        "`track_progress` must never appear — the documented all-write-tools "
        "tool-scope leak; the sentinel reports via `Write` to its own report "
        "file only"
    )


# ---------------------------------------------------------------------------
# (o) Publication is gated on the credential gate, and the flags an attacker or
# a careless edit would reach for stay closed. The action combines repeated
# `--allowedTools` flags and keeps the LAST `--settings`, so a single trailing
# flag can widen the grant or drop every kill switch while each earlier check
# still sees the original value.
# ---------------------------------------------------------------------------

CREDENTIAL_GATE_PASSED = "steps.credential_gate.outcome == 'success'"
JOB_TOKEN = "${{ github.token }}"
DEFAULT_BRANCH_REF = "${{ github.event.repository.default_branch }}"
SINGLE_USE_FLAGS = ("--allowedTools", "--allowed-tools", "--disallowedTools", "--settings")
BANNED_CLAUDE_ARGS = (
    "--permission-mode",
    "--mcp-config",
    "--dangerously-skip-permissions",
    "bypassPermissions",
)


def _publishing_steps(parsed: dict) -> list[dict]:
    """Steps that put report content where the public can read it."""
    return [
        step
        for step in _all_steps(parsed)
        if "upload-artifact" in (step.get("uses") or "")
        or "GITHUB_STEP_SUMMARY" in (step.get("run") or "")
    ]


def _assert_publication_requires_a_clear_credential_gate(parsed: dict) -> None:
    gate_ids = [step.get("id") for step in _all_steps(parsed)]
    assert "credential_gate" in gate_ids, (
        "The credential gate step must carry `id: credential_gate`"
    )
    publishing = _publishing_steps(parsed)
    assert publishing, "Expected a job-summary step and an upload step"
    for step in publishing:
        condition = str(step.get("if") or "")
        assert CREDENTIAL_GATE_PASSED in condition, (
            f"Step {step.get('name')!r} publishes report content but runs on "
            f"`if: {condition}` — it must require `{CREDENTIAL_GATE_PASSED}`, or a "
            "token-shaped string reaches the public summary and artifact after "
            "the gate has already failed"
        )


def _assert_github_token_is_the_job_token(parsed: dict) -> None:
    for step in _action_steps(parsed):
        assert (step.get("with") or {}).get("github_token") == JOB_TOKEN, (
            f"`github_token` must be exactly `{JOB_TOKEN}` (the job's contents: read "
            "token) — any other token, such as a PAT secret, escapes the job's "
            "permission ceiling"
        )


def _assert_claude_args_flags_are_single_and_unbanned(parsed: dict) -> None:
    combined = " ".join(_claude_args_blocks(parsed))
    for flag in SINGLE_USE_FLAGS:
        count = len(re.findall(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", combined))
        expected = 0 if flag == "--allowed-tools" else 1
        assert count == expected, (
            f"`{flag}` appears {count} times in claude_args (expected {expected}) — "
            "a repeated grant flag widens the tool set and a later `--settings` "
            "silently replaces the kill-switch payload"
        )
    for banned in BANNED_CLAUDE_ARGS:
        assert banned not in combined, (
            f"`{banned}` must never appear in claude_args — it bypasses the tool "
            "grant or starts MCP servers in the unattended session"
        )


def _assert_setup_uv_cache_is_disabled(parsed: dict) -> None:
    setup_uv = [s for s in _all_steps(parsed) if "setup-uv" in (s.get("uses") or "")]
    assert setup_uv, "Expected a setup-uv step"
    for step in setup_uv:
        value = (step.get("with") or {}).get("enable-cache")
        assert value in (False, "false"), (
            "setup-uv must set `enable-cache: false` — its post-step saves the cache "
            "after an unrestricted-Bash agent has run, and a write-scoped workflow "
            "can restore it"
        )


def _assert_no_step_output_is_interpolated_into_a_run_body(parsed: dict) -> None:
    for step in _all_steps(parsed):
        run = step.get("run") or ""
        assert "${{ steps." not in run, (
            f"Step {step.get('name')!r} interpolates a step output into its `run:` "
            "script — agent-influenced values (a report filename) must arrive "
            "through `env:`, never as shell source"
        )


def _assert_checkout_targets_the_default_branch(parsed: dict) -> None:
    checkouts = [s for s in _all_steps(parsed) if "actions/checkout" in (s.get("uses") or "")]
    assert checkouts, "Expected an actions/checkout step"
    for step in checkouts:
        assert (step.get("with") or {}).get("ref") == DEFAULT_BRANCH_REF, (
            f"checkout must pin `ref: {DEFAULT_BRANCH_REF}` — a dispatch from a "
            "feature branch would otherwise audit that branch, not main"
        )


def _mutate_publish_on_always(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _publishing_steps(mutated):
        step["if"] = "always()"
    return mutated


def _mutate_github_token_to_a_pat(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _action_steps(mutated):
        step.setdefault("with", {})["github_token"] = "${{ secrets.ADMIN_PAT }}"
    return mutated


def _append_claude_args(suffix: str):
    def mutate(parsed: dict) -> dict:
        mutated = copy.deepcopy(parsed)
        for step in _action_steps(mutated):
            with_block = step.setdefault("with", {})
            with_block["claude_args"] = with_block.get("claude_args", "") + suffix
        return mutated

    return mutate


def _mutate_enable_setup_uv_cache(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _all_steps(mutated):
        if "setup-uv" in (step.get("uses") or ""):
            step.setdefault("with", {}).pop("enable-cache", None)
    return mutated


def _mutate_interpolate_step_output_into_run(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _all_steps(mutated):
        if step.get("run"):
            step["run"] = 'echo "${{ steps.check_reports.outputs.new_report }}"\n' + step["run"]
            break
    return mutated


def _mutate_drop_checkout_ref(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _all_steps(mutated):
        if "actions/checkout" in (step.get("uses") or ""):
            (step.get("with") or {}).pop("ref", None)
    return mutated


def test_publication_requires_a_clear_credential_gate() -> None:
    _assert_publication_requires_a_clear_credential_gate(_parsed())


def test_github_token_is_the_job_token() -> None:
    _assert_github_token_is_the_job_token(_parsed())


def test_claude_args_flags_are_single_and_unbanned() -> None:
    _assert_claude_args_flags_are_single_and_unbanned(_parsed())


def test_setup_uv_cache_is_disabled() -> None:
    _assert_setup_uv_cache_is_disabled(_parsed())


def test_no_step_output_is_interpolated_into_a_run_body() -> None:
    _assert_no_step_output_is_interpolated_into_a_run_body(_parsed())


def test_checkout_targets_the_default_branch() -> None:
    _assert_checkout_targets_the_default_branch(_parsed())


def test_report_check_surfaces_a_non_success_agent_outcome() -> None:
    step = next(s for s in _all_steps(_parsed()) if s.get("id") == "check_reports")
    env = step.get("env") or {}
    assert "${{ steps.sentinel.outcome }}" in env.values(), (
        "The report check must receive the agent step's outcome — a run cut off "
        "by the turn cap or the timeout can leave a stub report that would "
        "otherwise pass silently"
    )
    assert "::warning::" in (step.get("run") or "")


# ---------------------------------------------------------------------------
# (p) No cache the agent can poison, a settings payload that only sets kill
# switches, and a state patch that reaches the artifact. The pinned action
# installs Bun through a nested setup-bun whose post-step saves a cache after
# the agent ran, under a key the write-scoped autofix workflows share; the
# workflow installs Bun itself with the cache off and hands the action the
# binary, which skips the nested install.
# ---------------------------------------------------------------------------

SETUP_BUN_SHA = "0c5077e51419868618aeaa5fe8019c62421857d6"  # oven-sh/setup-bun v2.2.0
STATE_PATCH = "/tmp/sentinel-state.patch"


def _assert_bun_is_installed_without_a_cache(parsed: dict) -> None:
    setup_bun = [s for s in _all_steps(parsed) if "oven-sh/setup-bun" in (s.get("uses") or "")]
    assert setup_bun, "Expected an explicit setup-bun step before the agent step"
    for step in setup_bun:
        assert step["uses"].split("@", 1)[1] == SETUP_BUN_SHA, (
            "setup-bun must use the same commit the pinned action nests"
        )
        assert (step.get("with") or {}).get("no-cache") in (True, "true"), (
            "setup-bun must set `no-cache: true` — its post-step would otherwise "
            "save a cache after the unrestricted-Bash agent ran"
        )
    bun_step_ids = {step.get("id") for step in setup_bun}
    for step in _action_steps(parsed):
        bun_path = str((step.get("with") or {}).get("path_to_bun_executable", ""))
        wired = [f"${{{{ steps.{i}.outputs.bun-path }}}}" for i in bun_step_ids if i]
        assert bun_path in wired, (
            f"`path_to_bun_executable` is {bun_path!r} — it must be the explicit "
            "setup-bun step's `bun-path` output; any other value (a typo'd output "
            "name resolves to empty) makes the action run its own nested setup-bun "
            "with the cache on"
        )


def _assert_settings_payload_only_sets_kill_switches(parsed: dict) -> None:
    payload = _settings_json(parsed)
    assert set(payload) == {"env"}, (
        f"The `--settings` payload carries {sorted(payload)} — only `env` is allowed; "
        "a `permissions` key grants tools beyond agents/sentinel.md without a prompt"
    )
    extra = set(payload["env"]) - set(KILL_SWITCH_FLAGS)
    assert not extra, f"The `--settings` env sets {sorted(extra)}, which are not kill switches"


def _mutate_enable_setup_bun_cache(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _all_steps(mutated):
        if "oven-sh/setup-bun" in (step.get("uses") or ""):
            step.setdefault("with", {}).pop("no-cache", None)
    return mutated


def _mutate_drop_bun_path(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _action_steps(mutated):
        (step.get("with") or {}).pop("path_to_bun_executable", None)
    return mutated


def _mutate_typo_bun_path_output(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _action_steps(mutated):
        step.setdefault("with", {})["path_to_bun_executable"] = "${{ steps.bun.outputs.bun_path }}"
    return mutated


def _mutate_grant_through_settings(parsed: dict) -> dict:
    mutated = copy.deepcopy(parsed)
    for step in _action_steps(mutated):
        with_block = step.get("with") or {}
        with_block["claude_args"] = with_block.get("claude_args", "").replace(
            "--settings '{", '--settings \'{"permissions":{"allow":["WebFetch"]},', 1
        )
    return mutated


def test_bun_is_installed_without_a_cache() -> None:
    _assert_bun_is_installed_without_a_cache(_parsed())


def test_settings_payload_only_sets_kill_switches() -> None:
    _assert_settings_payload_only_sets_kill_switches(_parsed())


def test_state_patch_is_built_from_the_log_and_ledger_and_uploaded() -> None:
    steps = _all_steps(_parsed())
    patch_step = next(s for s in steps if s.get("id") == "patch")
    run = patch_step.get("run") or ""
    assert STATE_PATCH in run
    lost_otherwise = (
        "The state patch must carry the log row and any ledger rows the sentinel "
        "appended — they are lost otherwise, since nothing is committed back"
    )
    assert "SENTINEL_LOG.md" in run, lost_otherwise
    assert "TECH_DEBT_LEDGER.md" in run, lost_otherwise
    upload = next(s for s in steps if "upload-artifact" in (s.get("uses") or ""))
    assert STATE_PATCH in str((upload.get("with") or {}).get("path", ""))


def test_report_check_keeps_the_last_new_report() -> None:
    step = next(s for s in _all_steps(_parsed()) if s.get("id") == "check_reports")
    run = step.get("run") or ""
    assert "tail -n 1 /tmp/new-reports.txt" in run, (
        "When the sentinel mints a second report it orphans the first; the "
        "completed report is the later file, so the check must keep the last one"
    )
    assert "head -n 1 /tmp/new-reports.txt" not in run


# ---------------------------------------------------------------------------
# Mutation canaries — one per workflow-specific security invariant. Each
# mutation flips the invariant from true to false; the paired predicate must
# reject the mutated parse. A canary that passes on both the real and the
# mutated workflow isn't actually checking anything.
# ---------------------------------------------------------------------------


MUTATION_CANARIES = [
    pytest.param(
        _mutate_add_pull_request_trigger,
        _assert_triggers_exact,
        id="adding_a_pull_request_trigger",
    ),
    pytest.param(
        _mutate_add_contents_write_permission,
        _assert_no_permission_block_grants_forbidden_keys,
        id="adding_a_contents_write_permission",
    ),
    pytest.param(
        _mutate_add_id_token_permission,
        _assert_no_permission_block_grants_forbidden_keys,
        id="adding_an_id_token_permission",
    ),
    pytest.param(
        _mutate_drop_github_token,
        _assert_github_token_present_on_action_step,
        id="dropping_github_token",
    ),
    pytest.param(
        _mutate_widen_allowed_tools_beyond_grant,
        _assert_allowed_tools_subset_of_sentinel_grant,
        id="widening_allowed_tools_beyond_the_sentinel_agents_grant",
    ),
    pytest.param(
        _mutate_publish_on_always,
        _assert_publication_requires_a_clear_credential_gate,
        id="publishing_after_a_failed_credential_gate",
    ),
    pytest.param(
        _mutate_github_token_to_a_pat,
        _assert_github_token_is_the_job_token,
        id="swapping_github_token_for_a_pat",
    ),
    pytest.param(
        _append_claude_args(' --allowed-tools "WebFetch"'),
        _assert_claude_args_flags_are_single_and_unbanned,
        id="appending_a_second_allowed_tools_flag",
    ),
    pytest.param(
        _append_claude_args(" --settings '{}'"),
        _assert_claude_args_flags_are_single_and_unbanned,
        id="appending_a_trailing_settings_flag",
    ),
    pytest.param(
        _append_claude_args(" --permission-mode bypassPermissions"),
        _assert_claude_args_flags_are_single_and_unbanned,
        id="appending_bypass_permissions",
    ),
    pytest.param(
        _append_claude_args(" --mcp-config extra.json"),
        _assert_claude_args_flags_are_single_and_unbanned,
        id="appending_an_mcp_config",
    ),
    pytest.param(
        _mutate_enable_setup_uv_cache,
        _assert_setup_uv_cache_is_disabled,
        id="re_enabling_the_setup_uv_cache",
    ),
    pytest.param(
        _mutate_interpolate_step_output_into_run,
        _assert_no_step_output_is_interpolated_into_a_run_body,
        id="interpolating_a_step_output_into_a_run_body",
    ),
    pytest.param(
        _mutate_drop_checkout_ref,
        _assert_checkout_targets_the_default_branch,
        id="dropping_the_checkout_ref",
    ),
    pytest.param(
        _mutate_enable_setup_bun_cache,
        _assert_bun_is_installed_without_a_cache,
        id="re_enabling_the_setup_bun_cache",
    ),
    pytest.param(
        _mutate_drop_bun_path,
        _assert_bun_is_installed_without_a_cache,
        id="letting_the_action_install_its_own_bun",
    ),
    pytest.param(
        _mutate_grant_through_settings,
        _assert_settings_payload_only_sets_kill_switches,
        id="granting_a_tool_through_the_settings_payload",
    ),
    pytest.param(
        _mutate_typo_bun_path_output,
        _assert_bun_is_installed_without_a_cache,
        id="miswiring_the_bun_path_output",
    ),
]


@pytest.mark.parametrize(("mutate", "predicate"), MUTATION_CANARIES)
def test_mutation_canary_bites_on_a_known_bad_workflow(mutate, predicate) -> None:
    mutated = mutate(_parsed())
    with pytest.raises(AssertionError):
        predicate(mutated)
