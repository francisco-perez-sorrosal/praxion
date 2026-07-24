"""Structural invariant tests for the Praxion issue-autofix workflow.

`.github/workflows/issue-autofix.yml` does not exist yet — these tests define
the security/interface contract the implementer must satisfy when building
the label-gated, triage-first fixer for `ecosystem-feedback` issues (Subsystem
C of the self-healing loop). Every test reads the file lazily (inside the
function body, not at module import time) so collection succeeds before the
file exists; running this module now is expected to fail — the first test
with a clear "file not found" assertion, the rest with an uncaught
`FileNotFoundError` raised while reading a file that is not there yet — but
never with an import error at collection time.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps, permission grants, and banned patterns. It cannot
verify runtime behavior (what the live `claude-code-action` actually does
under an `issues.labeled` event, whether the agent truly never self-arms in
production, whether a live dedup search finds a real duplicate) — those
guarantees close only via a live dogfood run in production CI. Where a test
is a structural proxy for a runtime guarantee, its docstring says so
explicitly.

Modeled directly on `tests/test_ci_autofix_hub_invariants.py` (the shipped
sibling covering the P1 hub) and the same-shape hub-invariant suite for the
P2 cross-model review gate — lazy file read, `_on_block`/`_jobs`/
`_all_steps`/`_uses_refs`/`_job_permissions` helper reuse, exact-permission-
dict assertions, and `_mentions_near` as a co-occurrence proxy for prompt-text
structural claims.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "issue-autofix.yml"

SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# The exact commits P1 (`reusable-ci-autofix.yml`) pins — P5 must match
# character-for-character, never re-resolve to a newer/older SHA.
CHECKOUT_SHA = "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"  # actions/checkout v7.0.0
SETUP_UV_SHA = "11f9893b081a58869d3b5fccaea48c9e9e46f990"  # astral-sh/setup-uv v8.3.2
CLAUDE_CODE_ACTION_SHA = (
    "51ea8ea73a139f2a74ff649e3092c25a904aed7e"  # anthropics/claude-code-action v1
)

# The exact, minimal permission set the fixer job may hold — no more, no less.
EXPECTED_JOB_PERMISSIONS = {
    "contents": "write",
    "pull-requests": "write",
    "issues": "write",
    "id-token": "write",
}

BLANKET_SHELL_PATTERNS = ("Bash(bash:*)", "Bash(sh:*)", "Bash(*)")


# ---------------------------------------------------------------------------
# Helpers
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
    This is a well-known GitHub-Actions-YAML gotcha; every lookup of the
    trigger block must account for it.
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


def _prompt_blocks(parsed: dict) -> list[str]:
    """Return every `with.prompt` string across all `claude-code-action` steps."""
    return [
        (step.get("with") or {}).get("prompt", "")
        for step in _all_steps(parsed)
        if "claude-code-action" in (step.get("uses") or "")
    ]


def _mentions_near(raw: str, term_a: str, term_b: str, window: int = 400) -> bool:
    """True if `term_a` and `term_b` co-occur within `window` chars, either order.

    A loose structural proxy: it does not pin the exact mechanism wiring the
    two concepts together, only that they appear near each other somewhere in
    the file.
    """
    pattern = re.compile(
        rf"({re.escape(term_a)}.{{0,{window}}}{re.escape(term_b)}"
        rf"|{re.escape(term_b)}.{{0,{window}}}{re.escape(term_a)})",
        re.IGNORECASE | re.DOTALL,
    )
    return bool(pattern.search(raw))


# ---------------------------------------------------------------------------
# Existence and parseability
# ---------------------------------------------------------------------------


def test_workflow_file_exists_and_parses_as_yaml() -> None:
    assert WORKFLOW_FILE.exists(), (
        f"{WORKFLOW_FILE} not found. The implementer must create the "
        "label-gated issue-autofix workflow."
    )
    parsed = _parsed()
    assert isinstance(parsed, dict), "Workflow must parse to a YAML mapping"


# ---------------------------------------------------------------------------
# Trigger contract — issues.labeled only, never pull_request_target
# ---------------------------------------------------------------------------


def test_trigger_is_issues_labeled_only() -> None:
    parsed = _parsed()
    on_block = _on_block(parsed)
    assert "issues" in on_block, (
        "Workflow's `on:` block must declare the `issues` event — this is a "
        "label-gated issue-triage workflow, not a workflow_run/PR trigger"
    )
    issues_block = on_block["issues"] or {}
    types = issues_block.get("types") or []
    assert "labeled" in types, (
        "`on.issues.types` must include `labeled` — the workflow arms on a "
        "label application, not issue creation/edit/etc."
    )


def test_never_triggers_on_pull_request_target() -> None:
    raw = _raw_text()
    assert "pull_request_target" not in raw, (
        "`pull_request_target` must never appear anywhere in this workflow — "
        "the trigger is `issues.labeled`, never a PR-context event that would "
        "run untrusted code with write credentials"
    )


# ---------------------------------------------------------------------------
# Arming gate — label literal AND non-Bot actor, joined by &&
# ---------------------------------------------------------------------------


def test_arming_gate_requires_exact_label_and_non_bot_sender() -> None:
    parsed = _parsed()
    jobs = _jobs(parsed)
    assert jobs, "Workflow must declare at least one job"
    conditions = [job.get("if") or "" for job in jobs.values()]
    matching = [
        c
        for c in conditions
        if "github.event.label.name == 'ecosystem-feedback'" in c
        and "github.event.sender.type != 'Bot'" in c
    ]
    assert matching, (
        "At least one job's `if:` must contain both "
        "`github.event.label.name == 'ecosystem-feedback'` and "
        "`github.event.sender.type != 'Bot'` — the two-layer arming gate "
        "(exact label literal + non-Bot actor guard)"
    )


def test_arming_gate_conjuncts_are_joined_by_and_not_or() -> None:
    """The two conjuncts must require BOTH conditions (&&), not either (||) —
    an || would let any label, or a Bot-applied label, arm the agent.
    """
    parsed = _parsed()
    jobs = _jobs(parsed)
    conditions = [job.get("if") or "" for job in jobs.values()]
    matching = [c for c in conditions if "ecosystem-feedback" in c and "sender.type" in c]
    assert matching, "Expected a job `if:` referencing both the label and the sender type"
    for condition in matching:
        assert "&&" in condition, (
            f"Arming gate {condition!r} must join label-name and sender-type "
            "checks with `&&` — an `||` would let any label, or a Bot, arm the agent"
        )
        assert "||" not in condition, (
            f"Arming gate {condition!r} must not contain `||` between the "
            "label-name and sender-type checks — that would defeat the gate"
        )


def test_agent_cannot_self_arm_via_its_own_label_applications() -> None:
    """Defense-in-depth: the load-bearing control against a self-arm loop is
    the actor guard, not the prompt. This asserts the actor guard is a
    structural condition, not merely prompt text advising against it.
    """
    parsed = _parsed()
    jobs = _jobs(parsed)
    conditions = [job.get("if") or "" for job in jobs.values()]
    assert any("sender.type" in c and "Bot" in c for c in conditions), (
        "The actor guard (`sender.type != 'Bot'`) must be a structural job "
        "`if:` condition — a prompt instruction alone is not a guarantee "
        "that the agent's own `claude[bot]` label applications cannot self-arm"
    )


# ---------------------------------------------------------------------------
# Concurrency — per-issue group, no cancel-in-progress
# ---------------------------------------------------------------------------


def test_concurrency_group_is_scoped_per_issue() -> None:
    parsed = _parsed()
    assert "concurrency" in parsed, (
        "Workflow must declare a top-level `concurrency:` group so two "
        "label events on the same issue never race to open conflicting fixes"
    )
    group = parsed["concurrency"].get("group") or ""
    assert "github.event.issue.number" in group, (
        "`concurrency.group` must key on `github.event.issue.number` — a "
        "workflow-wide (non-issue-scoped) group would serialize unrelated "
        "issues against each other unnecessarily"
    )


def test_concurrency_never_cancels_an_in_flight_run() -> None:
    parsed = _parsed()
    concurrency = parsed.get("concurrency") or {}
    assert concurrency.get("cancel-in-progress") is not True, (
        "`concurrency.cancel-in-progress` must not be `true` — a later label "
        "event killing an in-flight fix mid-way (e.g. mid-PR-creation) is "
        "exactly the race the concurrency group exists to prevent"
    )


# ---------------------------------------------------------------------------
# Least privilege — the fixer job's exact permission set
# ---------------------------------------------------------------------------


def test_fixer_job_permissions_are_exactly_the_four_declared_grants() -> None:
    parsed = _parsed()
    permissions = _job_permissions(parsed)
    assert permissions, "Workflow must declare at least one job with its own `permissions:`"
    assert any(perm == EXPECTED_JOB_PERMISSIONS for perm in permissions), (
        "The fixer job's own `permissions:` must be EXACTLY "
        f"{EXPECTED_JOB_PERMISSIONS} — no more, no less"
    )


def test_no_job_grants_actions_permission() -> None:
    parsed = _parsed()
    for perm in _job_permissions(parsed):
        assert "actions" not in perm, (
            "No job may hold an `actions:` permission grant — this job's "
            "surface is strictly smaller than P1's fixer (which needs "
            "`actions: read` to view CI run logs; this workflow has no "
            "analogous need)"
        )


def test_no_job_grants_broader_permissions_than_declared() -> None:
    """Every job's permission keys must be a subset of the four declared
    grants — catches an accidental extra key (e.g. `packages: write`) that
    the exact-dict test above would also catch, but this pins the failure to
    the specific offending key for a clearer diagnostic.
    """
    parsed = _parsed()
    allowed_keys = set(EXPECTED_JOB_PERMISSIONS)
    for perm in _job_permissions(parsed):
        extra_keys = set(perm) - allowed_keys
        assert not extra_keys, (
            f"Job `permissions:` grants unexpected key(s) {extra_keys} — only "
            f"{sorted(allowed_keys)} are permitted"
        )


# ---------------------------------------------------------------------------
# track_progress must never appear (bug #860 regression)
# ---------------------------------------------------------------------------


def test_never_references_track_progress() -> None:
    raw = _raw_text()
    assert "track_progress" not in raw, (
        "`track_progress` must never appear — this is the exact all-write-"
        "tools tool-scope leak bug #860 documented; the fixer must report "
        "triage status via plain `gh` steps only"
    )


# ---------------------------------------------------------------------------
# Supply-chain pinning — every uses: is a 40-hex SHA, matching P1's exact pins
# ---------------------------------------------------------------------------


def test_every_uses_reference_is_sha_pinned() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    assert (
        refs
    ), "Workflow must contain at least one `uses:` step (checkout, setup-uv, the fixer agent)"
    for ref in refs:
        assert "@" in ref, f"`uses: {ref}` must pin a ref via '@<sha>'"
        pinned_ref = ref.rsplit("@", 1)[1]
        assert SHA_PIN_PATTERN.match(pinned_ref), (
            f"`uses: {ref}` must be pinned to a full 40-hex-char commit SHA, "
            f"not a mutable tag or branch (got {pinned_ref!r})"
        )


def test_checkout_pin_matches_p1_exact_commit() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    matching = [ref for ref in refs if ref.startswith("actions/checkout@")]
    assert matching, "Expected an `actions/checkout` step"
    assert any(
        ref == f"actions/checkout@{CHECKOUT_SHA}" for ref in matching
    ), f"actions/checkout must pin to P1's exact commit {CHECKOUT_SHA} (got {matching})"


def test_setup_uv_pin_matches_p1_exact_commit() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    matching = [ref for ref in refs if ref.startswith("astral-sh/setup-uv@")]
    assert matching, "Expected an `astral-sh/setup-uv` step"
    assert any(
        ref == f"astral-sh/setup-uv@{SETUP_UV_SHA}" for ref in matching
    ), f"astral-sh/setup-uv must pin to P1's exact commit {SETUP_UV_SHA} (got {matching})"


def test_claude_code_action_pin_matches_p1_exact_commit() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    matching = [ref for ref in refs if ref.startswith("anthropics/claude-code-action@")]
    assert matching, "Expected an `anthropics/claude-code-action` step"
    assert any(
        ref == f"anthropics/claude-code-action@{CLAUDE_CODE_ACTION_SHA}" for ref in matching
    ), (
        f"anthropics/claude-code-action must pin to P1's exact commit "
        f"{CLAUDE_CODE_ACTION_SHA} (got {matching})"
    )


# ---------------------------------------------------------------------------
# Daily budget gate + idempotency guard
# ---------------------------------------------------------------------------


def test_daily_budget_gate_step_exists() -> None:
    parsed = _parsed()
    steps = _all_steps(parsed)
    step_names = " ".join((step.get("name") or "").lower() for step in steps)
    step_runs = " ".join((step.get("run") or "").lower() for step in steps)
    assert "budget" in step_names or "budget" in step_runs, (
        "A daily-run-budget-gate step must exist, mirroring "
        "reusable-ci-autofix.yml's mechanism, so a label-spam or rubber-"
        "stamp burst cannot run away on cost"
    )


def test_idempotency_guard_checks_terminal_labels_or_open_pr() -> None:
    raw = _raw_text()
    assert _mentions_near(raw, "triage:invalid", "duplicate") or (
        "triage:invalid" in raw and "duplicate" in raw
    ), (
        "An idempotency-guard step must check for the terminal triage labels "
        "(`triage:invalid`, `duplicate`, `needs-adr`) so re-applying "
        "`ecosystem-feedback` to an already-triaged issue is a no-op"
    )
    assert (
        "needs-adr" in raw
    ), "The idempotency guard must also recognize the `needs-adr` terminal label"
    assert "issue-autofix/" in raw, (
        "The idempotency guard must also check for an already-open "
        "`issue-autofix/*` PR referencing the issue"
    )


# ---------------------------------------------------------------------------
# Non-agent fetch + sanitize — issue body/title never reach the prompt raw
# ---------------------------------------------------------------------------


def test_issue_body_fetch_step_is_non_agent() -> None:
    parsed = _parsed()
    fetch_steps = [
        step for step in _all_steps(parsed) if "gh issue view" in (step.get("run") or "")
    ]
    assert fetch_steps, (
        "A plain shell step must fetch the issue body/title via `gh issue "
        "view` (or equivalent), not an agent action"
    )
    for step in fetch_steps:
        assert "uses" not in step, (
            "The issue-fetch step must be a `run:` step, not a `uses:` agent "
            "action — the issue body is written to a file for the agent to "
            "read as DATA, never interpolated into its instructions"
        )


def test_raw_issue_body_and_title_never_appear_in_a_prompt_block() -> None:
    parsed = _parsed()
    prompts = _prompt_blocks(parsed)
    assert prompts, "Expected at least one `claude-code-action` step with a `prompt:`"
    for prompt in prompts:
        assert "github.event.issue.body" not in prompt, (
            "The agent `prompt:` must never interpolate "
            "`github.event.issue.body` directly — untrusted issue text must "
            "reach the agent only via the non-agent-fetched, sanitized file"
        )
        assert "github.event.issue.title" not in prompt, (
            "The agent `prompt:` must never interpolate "
            "`github.event.issue.title` directly — same rationale as the body"
        )


def test_fetch_output_is_sanitized_before_the_agent_reads_it() -> None:
    """Structural proxy: asserts sanitization is documented OR mechanically
    performed somewhere in the workflow — the exact mechanism (ANSI-strip,
    truncation) is an implementer choice.
    """
    raw = _raw_text()
    assert re.search(r"saniti|truncat|\\x1b|cut -c|head -c|strip", raw, re.IGNORECASE), (
        "The fetched issue body/title must be sanitized (e.g. ANSI-escape "
        "stripped, truncated) before the agent reads it as data"
    )


def test_prompt_frames_issue_content_as_untrusted_data() -> None:
    parsed = _parsed()
    prompts = _prompt_blocks(parsed)
    assert prompts, "Expected at least one `claude-code-action` step with a `prompt:`"
    combined = " ".join(prompts)
    assert re.search(r"untrusted", combined, re.IGNORECASE), (
        "The agent-facing prompt must explicitly frame the fetched issue "
        "content as untrusted DATA (prompt-injection mitigation)"
    )
    assert re.search(r"instruction", combined, re.IGNORECASE), (
        "The agent-facing prompt must explicitly distinguish issue content "
        "from instructions (prompt-injection mitigation)"
    )


# ---------------------------------------------------------------------------
# Template-validate + dedup — malformed/duplicate issues never reach the agent
# ---------------------------------------------------------------------------


def test_template_validate_step_references_the_triage_module() -> None:
    raw = _raw_text()
    assert "issue_triage" in raw, (
        "A template-validate step must import from the "
        "`scripts.praxion_feedback.issue_triage` module (missing_required_"
        "sections / extract_fingerprint) rather than re-implementing "
        "validation logic inline"
    )


def test_malformed_issue_gets_triage_invalid_label() -> None:
    raw = _raw_text()
    assert (
        "triage:invalid" in raw
    ), "A malformed issue (missing required §5.2 sections) must be labeled `triage:invalid`"


def test_duplicate_issue_gets_duplicate_label() -> None:
    raw = _raw_text()
    assert "duplicate" in raw, "A fingerprint-matched issue must be labeled `duplicate`"


def test_dedup_search_excludes_the_current_issue() -> None:
    raw = _raw_text()
    assert "gh issue list" in raw, "A dedup step must search existing issues via `gh issue list`"


# ---------------------------------------------------------------------------
# Bash allowlist — no blanket shell, no gh issue create / gh run view
# ---------------------------------------------------------------------------


def test_allowed_tools_declares_no_blanket_shell_pattern() -> None:
    parsed = _parsed()
    claude_args_blocks = _claude_args_blocks(parsed)
    assert claude_args_blocks, "Expected at least one `claude-code-action` step with `claude_args`"
    for block in claude_args_blocks:
        for banned in BLANKET_SHELL_PATTERNS:
            assert banned not in block, (
                f"`claude_args` must never contain the blanket-shell pattern "
                f"{banned!r} — this would let the untrusted reproduction "
                "command escape the enumerated allowlist entirely"
            )


def test_allowed_tools_is_an_enumerated_git_gh_pytest_set() -> None:
    parsed = _parsed()
    claude_args_blocks = _claude_args_blocks(parsed)
    assert claude_args_blocks, "Expected at least one `claude-code-action` step with `claude_args`"
    combined = " ".join(claude_args_blocks)

    # Scoped git patterns — every allowed git subcommand must carry its own
    # `Bash(git <subcommand>:*)` entry, never a bare `Bash(git:*)`.
    # `checkout`/`branch` are DELIBERATELY excluded (see the dedicated
    # test_allowed_tools_excludes_git_checkout_and_git_branch) — the fix branch
    # is pre-created by a non-agent step, so the agent needs no branch tooling.
    assert "Bash(git:*)" not in combined, (
        "`claude_args` must never grant a bare `Bash(git:*)` — every git "
        "subcommand the fixer needs must be individually enumerated"
    )
    for git_subcommand in ("add", "commit", "status", "diff"):
        assert f"Bash(git {git_subcommand}:*)" in combined, (
            f"`claude_args` must enumerate `Bash(git {git_subcommand}:*)` "
            "among the scoped git patterns"
        )

    # Scoped gh patterns — same discipline for gh.
    assert "Bash(gh:*)" not in combined, (
        "`claude_args` must never grant a bare `Bash(gh:*)` — every gh "
        "subcommand the fixer needs must be individually enumerated"
    )

    # Test-runner patterns — at least one recognizable pytest invocation form.
    assert re.search(r"Bash\(([\w./]*\s+)?pytest:\*\)", combined), (
        "`claude_args` must allowlist at least one pytest-invocation pattern "
        "(e.g. `Bash(pytest:*)`, `Bash(uv run pytest:*)`, "
        "`Bash(python3 -m pytest:*)`)"
    )


def test_allowed_tools_excludes_gh_issue_create() -> None:
    parsed = _parsed()
    claude_args_blocks = _claude_args_blocks(parsed)
    combined = " ".join(claude_args_blocks)
    assert "Bash(gh issue create:*)" not in combined, (
        "`claude_args` must not allowlist `gh issue create` — P5 never files "
        "new issues, only labels/comments on the triggering one"
    )


def test_allowed_tools_excludes_gh_run_view() -> None:
    parsed = _parsed()
    claude_args_blocks = _claude_args_blocks(parsed)
    combined = " ".join(claude_args_blocks)
    assert "Bash(gh run view:*)" not in combined, (
        "`claude_args` must not allowlist `gh run view` — unlike the P1 "
        "fixer (which reads failed CI run logs), P5's fixer has no run-log "
        "reading need"
    )


# ---------------------------------------------------------------------------
# No unscoped push — the fixer opens a PR, it never pushes to the default branch
# ---------------------------------------------------------------------------


def test_allowed_tools_never_grants_a_blanket_git_push() -> None:
    parsed = _parsed()
    claude_args_blocks = _claude_args_blocks(parsed)
    combined = " ".join(claude_args_blocks)
    assert "Bash(git push:*)" not in combined, (
        "`claude_args` must never allowlist a blanket `Bash(git push:*)` — "
        "the design pushes the fix branch implicitly via `gh pr create`, so "
        "no explicit push pattern should exist at all"
    )


def test_allowed_tools_excludes_git_checkout_and_git_branch() -> None:
    """The agent must hold no branch-switching or branch-creating tool.

    The fix branch is pre-created and checked out by a deterministic non-agent
    step, so the agent starts on it. Without `git checkout`/`git branch` in the
    allowlist, the agent cannot switch back to the checked-out default branch
    (which `actions/checkout` leaves as a local branch named after it) and
    commit onto it — closing the reach-`main` vector STRUCTURALLY rather than
    relying on the prompt. On this repo the default branch carries no
    protection, so the allowlist is the load-bearing gate.
    """
    parsed = _parsed()
    claude_args_blocks = _claude_args_blocks(parsed)
    assert claude_args_blocks, "Expected at least one `claude-code-action` step with `claude_args`"
    combined = " ".join(claude_args_blocks)
    assert "Bash(git checkout:*)" not in combined, (
        "`claude_args` must NOT allowlist `Bash(git checkout:*)` — the fix "
        "branch is pre-created by a non-agent step; granting checkout would let "
        "the agent switch back to the checked-out default branch and commit "
        "onto it, then push it via `gh pr create`"
    )
    assert "Bash(git branch:*)" not in combined, (
        "`claude_args` must NOT allowlist `Bash(git branch:*)` — the fix branch "
        "is pre-created by a non-agent step; the agent never creates branches"
    )


def test_no_step_pushes_directly_to_the_default_branch() -> None:
    raw = _raw_text()
    assert not re.search(r"git push\s+[^\n]*\bmain\b", raw), (
        "No step may run `git push` targeting `main` — a direct commit to "
        "the default branch would re-trigger the very workflow the fix is "
        "meant to address, and bypasses the human-merge gate entirely"
    )


def test_non_agent_branch_creation_step_precedes_the_agent() -> None:
    """A deterministic non-agent `run:` step must create + check out the fix
    branch BEFORE the `claude-code-action` step.

    Combined with the absence of `git checkout`/`git branch` in the agent's
    allowlist, this is what structurally prevents the agent from reaching the
    (unprotected) default branch: it can only ever be on the pre-created fix
    branch, which leaves the runner solely via `gh pr create`. If the agent
    created its own branch, a prompt-injection or ordering error could leave it
    on the default branch instead.
    """
    parsed = _parsed()
    steps = _all_steps(parsed)

    branch_idx: int | None = None
    agent_idx: int | None = None
    for idx, step in enumerate(steps):
        run = step.get("run") or ""
        uses = step.get("uses") or ""
        if branch_idx is None and re.search(r"git checkout -b\s+.*issue-autofix/", run):
            branch_idx = idx
        if agent_idx is None and "claude-code-action" in uses:
            agent_idx = idx

    assert branch_idx is not None, (
        "A non-agent `run:` step must create + check out the fix branch "
        "(`git checkout -b issue-autofix/<n>-...`) — the agent must start on a "
        "pre-created branch, never create its own"
    )
    assert agent_idx is not None, "Expected a `claude-code-action` step"
    assert "uses" not in steps[branch_idx], (
        "The branch-creation step must be a plain `run:` step, not a `uses:` "
        "action — branch creation must not be delegated to the agent"
    )
    assert branch_idx < agent_idx, (
        "The non-agent branch-creation step must PRECEDE the "
        "`claude-code-action` step so the agent starts on the pre-created "
        "fix branch, not the default branch"
    )


def test_prompt_forbids_pushing_to_the_default_branch() -> None:
    parsed = _parsed()
    prompts = _prompt_blocks(parsed)
    assert prompts, "Expected at least one `claude-code-action` step with a `prompt:`"
    combined = " ".join(prompts).lower()
    assert re.search(r"never push", combined) or re.search(r"do not push", combined), (
        "The agent-facing prompt must explicitly instruct the fixer to never "
        "push to the default branch"
    )


# ---------------------------------------------------------------------------
# Mechanical vs behavioral/architectural classification
# ---------------------------------------------------------------------------


def test_prompt_references_the_mechanical_fix_pr_path() -> None:
    parsed = _parsed()
    prompts = _prompt_blocks(parsed)
    combined = " ".join(prompts)
    assert "issue-autofix/" in combined, (
        "The prompt must instruct the fixer to branch as `issue-autofix/<n>-"
        "<slug>` for mechanical fixes"
    )
    assert "Fixes #" in combined, (
        "The prompt must instruct the fixer to include `Fixes #<n>` in the "
        "PR body so the issue auto-closes on merge"
    )


def test_prompt_references_the_behavioral_needs_adr_path() -> None:
    parsed = _parsed()
    prompts = _prompt_blocks(parsed)
    combined = " ".join(prompts)
    assert "needs-adr" in combined, (
        "The prompt must instruct the fixer to apply `needs-adr` (and post a "
        "root-cause comment, no PR) for behavioral/architectural defects"
    )


def test_prompt_distinguishes_mechanical_from_behavioral() -> None:
    parsed = _parsed()
    prompts = _prompt_blocks(parsed)
    combined = " ".join(prompts).lower()
    assert "mechanical" in combined, "The prompt must name the 'mechanical' classification"
    assert "behavioral" in combined or "architectural" in combined, (
        "The prompt must name the 'behavioral'/'architectural' classification "
        "as the alternative to 'mechanical'"
    )


# ---------------------------------------------------------------------------
# Deny-by-default governance surfaces
# ---------------------------------------------------------------------------


def test_prompt_names_the_deny_by_default_governance_surfaces() -> None:
    parsed = _parsed()
    prompts = _prompt_blocks(parsed)
    combined = " ".join(prompts)
    for surface in (".ai-state/decisions/", "agents/", "rules/"):
        assert surface in combined, (
            f"The prompt must name {surface!r} among the governance surfaces "
            "that force a behavioral/architectural classification (never "
            "auto-fixed as mechanical)"
        )
    assert re.search(
        r"skill", combined, re.IGNORECASE
    ), "The prompt must reference skills' `SKILL.md` core among the governance surfaces"
    assert re.search(r"behavioral contract", combined, re.IGNORECASE), (
        "The prompt must reference the behavioral contract among the "
        "governance surfaces that force escalation"
    )


# ---------------------------------------------------------------------------
# Sensitive-path tripwire — reused from P1, adapted branch prefix
# ---------------------------------------------------------------------------


def test_sensitive_path_tripwire_step_exists() -> None:
    parsed = _parsed()
    steps = _all_steps(parsed)
    step_names = " ".join((step.get("name") or "").lower() for step in steps)
    step_runs = " ".join((step.get("run") or "").lower() for step in steps)
    assert "sensitive" in step_names or "sensitive" in step_runs, (
        "A sensitive-path tripwire step must exist, converting a PR to draft "
        "and requesting mandatory human review when it touches CI/automation "
        "surfaces"
    )


def test_sensitive_path_tripwire_targets_the_issue_autofix_branch_prefix() -> None:
    """Strengthened: the `issue-autofix/` prefix selection must live INSIDE the
    tripwire step's own `run:` body, not merely somewhere in the file.

    A bare file-level grep for `issue-autofix/` is already satisfied by the
    idempotency guard, the non-agent branch-creation step, and the agent prompt,
    so it cannot prove the tripwire selects the PRs this workflow actually opens.
    Reusing P1's `ci-autofix/` literal unmodified would never match, so the
    tripwire would silently never fire. (Red until the Step-10 tripwire lands —
    intentional, alongside the other two `test_sensitive_path_tripwire_*`.)
    """
    parsed = _parsed()
    steps = _all_steps(parsed)
    tripwire_steps = [
        step
        for step in steps
        if "sensitive" in (step.get("name") or "").lower()
        or "sensitive" in (step.get("run") or "").lower()
    ]
    assert (
        tripwire_steps
    ), "A sensitive-path tripwire step must exist (see test_sensitive_path_tripwire_step_exists)"
    assert any("issue-autofix/" in (step.get("run") or "") for step in tripwire_steps), (
        "The sensitive-path tripwire step must select PRs by this workflow's "
        "own `issue-autofix/*` branch prefix inside its OWN `run:` body — "
        "reusing P1's `ci-autofix/` literal unmodified would never match any "
        "PR this workflow opens, so the tripwire would silently never fire"
    )


def test_sensitive_path_tripwire_toggles_draft_via_gh_pr_ready_undo() -> None:
    raw = _raw_text()
    assert "gh pr ready" in raw, "The tripwire must call `gh pr ready` to toggle draft state"
    assert (
        "--undo" in raw
    ), "The draft toggle must use `--undo` (mark as draft), not the default (mark ready)"


# ---------------------------------------------------------------------------
# No AI authorship in fixer commits
# ---------------------------------------------------------------------------


def test_prompt_forbids_ai_authorship_commit_lines() -> None:
    parsed = _parsed()
    prompts = _prompt_blocks(parsed)
    combined = " ".join(prompts)
    assert re.search(r"Co-Authored-By", combined, re.IGNORECASE), (
        "The prompt must name `Co-Authored-By` as a forbidden commit-message "
        "line — silence on this is not the same as forbidding it"
    )
    assert re.search(
        r"no ai authorship|never.{0,40}ai authorship|no AI-authorship", combined, re.IGNORECASE
    ) or (
        "Co-Authored-By" in combined and re.search(r"never|no\b|not\b", combined, re.IGNORECASE)
    ), (
        "The prompt must explicitly forbid AI-authorship commit lines, not "
        "merely mention them descriptively"
    )


# ---------------------------------------------------------------------------
# gh's embedded jq does not support --arg (runtime-semantics guard)
# ---------------------------------------------------------------------------


def test_gh_jq_calls_do_not_use_the_unsupported_arg_flag() -> None:
    # `gh ... --jq`/`-q` runs a built-in jq that, unlike the standalone `jq`
    # CLI, does NOT accept `--arg name value` to bind a variable. Passing it
    # makes `gh` treat the flag + value + expression as unknown positional
    # arguments and exit 1 at runtime — invisible to YAML-structure checks.
    # Interpolate shell values into the jq string instead.
    raw = _raw_text()
    unsupported = "does not support jq's `--arg`; interpolate the shell value into the jq string"
    assert "--jq --arg" not in raw, f"`gh --jq {unsupported}"
    assert "-q --arg" not in raw, f"`gh -q {unsupported}"
