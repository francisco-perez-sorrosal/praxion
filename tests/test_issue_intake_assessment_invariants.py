"""Structural invariant tests for the cross-model issue-intake assessment gate.

`.github/workflows/issue-intake-assessment.yml` does not exist yet — these
tests define the security/interface contract the implementer must satisfy
when building it as the read-only assessment peer of the shipped
`issue-autofix.yml`. The intake gate's privilege ceiling is even narrower
than the fixer's: it holds `issues: write` + `contents: read` only, and must
be structurally incapable of opening a PR, pushing code, or applying any of
the autofix workflow's owned arming/triage labels.

Every test reads the file lazily (inside the function body, not at module
import time) so collection succeeds before the file exists; running this
module now is expected to fail with clear "file not found" / missing-structure
assertions on every test, never with an import error at collection time.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps, permission grants, and banned patterns. It cannot
verify runtime behavior (what a real Cursor CLI invocation actually returns,
whether the live `--list-models`/`--output-format json` envelope shape
matches what is assumed here, or whether `github.event.issue.labels`
reliably carries the expected labels on the `issues.opened` payload). Where a
test is a structural proxy for a runtime guarantee, its docstring says so
explicitly — those guarantees close only via a live dogfood run in
production CI, once a real Cursor round-trip is exercised end to end on a
real filed issue.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTAKE_WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "issue-intake-assessment.yml"

SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ADD_LABEL_PATTERN = re.compile(r"""--add-label\s+["']?([A-Za-z0-9:_-]+)["']?""")

# The exact commits already pinned repo-wide for these two actions (verified
# by grepping every other workflow file in `.github/workflows/`) — the
# intake gate must pin the same commits, not merely "a" 40-hex SHA, so a
# stale/wrong commit introduced during copy-paste is caught.
CHECKOUT_PIN = "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
SETUP_UV_PIN = "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990"

# The autofix workflow's own owned arming/triage labels — the intake gate
# must never be the one that applies any of these via `--add-label`.
FORBIDDEN_ARMING_LABELS = ("ecosystem-feedback", "needs-adr", "triage:invalid", "duplicate")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_text() -> str:
    """Return the intake gate's raw file content (read lazily so collection succeeds)."""
    return INTAKE_WORKFLOW_FILE.read_text(encoding="utf-8")


def _parsed() -> dict:
    """Parse the intake gate workflow as YAML."""
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
    raise AssertionError("Intake gate workflow has no `on:` trigger block")


def _jobs(parsed: dict) -> dict:
    """Return the workflow's `jobs:` mapping."""
    return parsed.get("jobs") or {}


def _job(parsed: dict) -> dict:
    """Return the intake gate's single job definition.

    The intake gate is designed as a single-job workflow (mirroring
    `issue-autofix.yml`'s own single-job `triage-and-fix` structure) — every
    structural bullet in the plan refers to "the job's" `if:`/`permissions:`,
    so a single job is the expected shape, not an implementation detail this
    suite should stay silent about.
    """
    jobs = _jobs(parsed)
    assert jobs, "Intake gate workflow must declare at least one job"
    assert len(jobs) == 1, (
        f"Expected exactly one job in the intake gate workflow, found {len(jobs)}: {sorted(jobs)}"
    )
    return next(iter(jobs.values()))


def _all_steps(parsed: dict) -> list[dict]:
    """Flatten every step across every job in the workflow."""
    steps: list[dict] = []
    for job in _jobs(parsed).values():
        steps.extend(job.get("steps") or [])
    return steps


def _uses_refs(parsed: dict) -> list[str]:
    """Collect every `uses:` value across every job/step in the workflow."""
    return [step["uses"] for step in _all_steps(parsed) if step.get("uses")]


def _all_permission_blocks(parsed: dict) -> list[dict]:
    """Return every `permissions:` mapping in the file — workflow-level and per-job."""
    blocks: list[dict] = []
    if "permissions" in parsed:
        blocks.append(parsed["permissions"] or {})
    for job in _jobs(parsed).values():
        blocks.append(job.get("permissions") or {})
    return blocks


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


def test_intake_workflow_file_exists_and_parses_as_yaml() -> None:
    assert INTAKE_WORKFLOW_FILE.exists(), (
        f"{INTAKE_WORKFLOW_FILE} not found. The implementer must create the "
        "intake gate as the read-only assessment peer of issue-autofix.yml."
    )
    parsed = _parsed()
    assert isinstance(parsed, dict), "Intake gate workflow must parse to a YAML mapping"


# ---------------------------------------------------------------------------
# Trigger — direct `on: issues`, never a reusable hub
# ---------------------------------------------------------------------------


def test_on_block_declares_direct_issues_trigger_with_opened_and_labeled_types() -> None:
    parsed = _parsed()
    on_block = _on_block(parsed)
    assert "issues" in on_block, (
        "Intake gate must be a direct `on: issues` workflow — it has no "
        "fleet consumer in v1 and must never be a `workflow_call` hub"
    )
    assert "workflow_call" not in on_block, (
        "Intake gate is Praxion-only in v1 — it must never declare `workflow_call`"
    )
    issues_block = on_block["issues"] or {}
    types = issues_block.get("types") or []
    assert "opened" in types, "`on.issues.types` must include `opened`"
    assert "labeled" in types, (
        "`on.issues.types` must include `labeled` — the fallback path for "
        "when labels are not reliably present on the `opened` payload"
    )


# ---------------------------------------------------------------------------
# Trigger gate — the exact `if:` predicate
# ---------------------------------------------------------------------------


def test_job_if_predicate_gates_only_on_the_two_stable_labels() -> None:
    """The job `if:` is pure event-payload context — no policy-file lookup.

    Mirrors `issue-autofix.yml`'s own job-level `if:` precedent (event facts
    only, e.g. `github.event.label.name == 'ecosystem-feedback'`), and
    `reusable-cross-model-review.yml`'s `review` job, which carries NO
    job-level `if:` at all. A job's `if:` is evaluated before any step runs,
    so it cannot see a step's output — the authoritative `intake_gate`
    policy value is instead enforced entirely via
    `steps.scope.outputs.should_assess`, asserted below.
    """
    parsed = _parsed()
    job = _job(parsed)
    if_expr = job.get("if") or ""
    assert if_expr, "The intake gate's job must declare an `if:` predicate"
    assert "auto-filed" in if_expr, "The job's `if:` must check for the `auto-filed` label"
    assert "from-managed-project" in if_expr, (
        "The job's `if:` must check for the `from-managed-project` label"
    )
    assert "&&" in if_expr, (
        "The two label checks must be joined by `&&` — both must hold for the job to run"
    )
    assert "vars." not in if_expr, (
        "The job's `if:` must never reference a `vars.*` Actions Variable — "
        "there is zero precedent for this elsewhere in the repo, and the "
        "authoritative gate is the policy-file `intake_gate` value, enforced "
        "via `steps.scope.outputs.should_assess`, not a job-level `if:`"
    )
    assert "intake_gate" not in if_expr, (
        "The job's `if:` must not reference `intake_gate` directly — that "
        "policy value is read from `.github/autofix-policy.yml` by the "
        "'Read review policy' step and enforced downstream via "
        "`steps.scope.outputs.should_assess`, not at the job level"
    )


def test_should_assess_output_gates_every_substantive_step() -> None:
    """The authoritative `intake_gate` policy gate lives at step level.

    Mirrors `reusable-cross-model-review.yml`'s `steps.gate.outputs.
    should_review` pattern: a dedicated step computes a boolean from the
    fail-safe-parsed policy value, and every substantive step downstream
    references that boolean in its own `if:`.
    """
    parsed = _parsed()
    job = _job(parsed)
    steps = job.get("steps") or []

    scope_step = next((s for s in steps if s.get("id") == "scope"), None)
    assert scope_step is not None, (
        "A step with id `scope` must compute `should_assess` from the "
        "policy-parsed `intake_gate` value"
    )
    scope_run = scope_step.get("run") or ""
    assert "should_assess" in scope_run, "The `scope` step must set a `should_assess` output"

    substantive_step_names = {
        "fetch-issue",
        "fetch-prism",
        "resolve",
        "assess",
    }
    substantive_steps = {s["id"]: s for s in steps if s.get("id") in substantive_step_names}
    assert substantive_step_names <= substantive_steps.keys(), (
        f"Expected substantive steps {sorted(substantive_step_names)}, "
        f"found {sorted(substantive_steps.keys())}"
    )
    for step_id, step in substantive_steps.items():
        step_if = step.get("if") or ""
        assert "steps.scope.outputs.should_assess" in step_if, (
            f"Step `{step_id}` must gate on `steps.scope.outputs.should_assess` "
            f"in its own `if:` — got {step_if!r}"
        )


# ---------------------------------------------------------------------------
# Permission ceiling — the single most important structural invariant here.
# A ceiling wider than issues:write + contents:read would let the intake
# gate open a PR or write code, collapsing the entire read-only design.
# ---------------------------------------------------------------------------


def test_job_permissions_are_exactly_issues_write_and_contents_read() -> None:
    parsed = _parsed()
    job = _job(parsed)
    permissions = job.get("permissions") or {}
    assert permissions == {"issues": "write", "contents": "read"}, (
        f"Intake gate job permissions must be EXACTLY `issues: write` + "
        f"`contents: read` — no more, no less. Got {permissions!r}"
    )


def test_no_permissions_block_anywhere_grants_pull_requests() -> None:
    parsed = _parsed()
    for perm in _all_permission_blocks(parsed):
        assert "pull-requests" not in perm, (
            "No permissions block in the intake gate may grant "
            "`pull-requests` — the gate must be structurally incapable of "
            "opening a PR"
        )


def test_no_permissions_block_anywhere_grants_contents_write() -> None:
    parsed = _parsed()
    for perm in _all_permission_blocks(parsed):
        assert perm.get("contents") != "write", (
            "No permissions block in the intake gate may hold "
            "`contents: write` — the gate must never be able to write code"
        )


def test_no_permissions_block_anywhere_grants_id_token() -> None:
    parsed = _parsed()
    for perm in _all_permission_blocks(parsed):
        assert "id-token" not in perm, (
            "No permissions block in the intake gate may hold `id-token` — "
            "OIDC-exchange capability belongs to the fixer workflow only"
        )


def test_never_opens_a_pr_or_writes_code() -> None:
    raw = _raw_text()
    assert "gh pr " not in raw, (
        "The intake gate must never invoke `gh pr` — it never opens, edits, "
        "or comments on a pull request"
    )
    assert "git push" not in raw, "The intake gate must never run `git push`"
    assert "git commit" not in raw, "The intake gate must never run `git commit`"
    assert "git checkout -b" not in raw, (
        "The intake gate must never run `git checkout -b` — it creates no branch"
    )


# ---------------------------------------------------------------------------
# Assessment JSON schema — the structured second-model opinion the human
# arming decision reads before acting.
# ---------------------------------------------------------------------------


def test_assessment_json_schema_fields_appear_in_the_workflow() -> None:
    raw = _raw_text()
    for field in ("assessment", "in_scope", "confidence", "rationale"):
        assert field in raw, (
            f"Assessment schema field `{field}` must appear in the reviewer "
            "prompt and/or the parse-and-act script"
        )


def test_assessment_json_schema_enum_values_appear_in_the_workflow() -> None:
    raw = _raw_text()
    for value in ("defect", "improvement", "non-issue", "unclear", "high", "medium", "low"):
        assert value in raw, (
            f"Assessment enum value `{value}` must appear in the reviewer "
            "prompt and/or the parse-and-act script"
        )


# ---------------------------------------------------------------------------
# Never arms — the intake gate informs the human, it never triggers the
# autofix workflow or the human arming semantics itself.
# ---------------------------------------------------------------------------


def test_never_applies_any_autofix_owned_arming_label() -> None:
    raw = _raw_text()
    applied_labels = set(ADD_LABEL_PATTERN.findall(raw))
    for forbidden in FORBIDDEN_ARMING_LABELS:
        assert forbidden not in applied_labels, (
            f"The intake gate must NEVER pass `{forbidden}` to `--add-label` "
            "— it is one of the autofix workflow's owned arming/triage "
            "labels; the intake gate may only apply cosmetic "
            "`intake-assessment:*`/`intake:*` labels"
        )


# ---------------------------------------------------------------------------
# Fail-open — every failure path converges on `unavailable`, exit 0.
# ---------------------------------------------------------------------------


def test_fail_open_owner_step_is_gated_on_always_and_converges_to_unavailable() -> None:
    parsed = _parsed()
    owner_steps = [step for step in _all_steps(parsed) if "always()" in (step.get("if") or "")]
    assert owner_steps, (
        "The intake gate must have an owner step gated `if: always()` that "
        "converges every upstream failure to a neutral outcome"
    )
    raw = _raw_text()
    assert "intake-assessment:unavailable" in raw, (
        "Every fail-open path (Cursor error, timeout, malformed JSON, no "
        "model of the configured family) must converge on the "
        "`intake-assessment:unavailable` label"
    )
    assert "gh issue comment" in raw, (
        "The owner step must post exactly one `gh issue comment` regardless of outcome"
    )


def test_no_failure_path_exits_non_zero() -> None:
    """Structural proxy for the fail-open guarantee: real runtime behavior —
    that every combination of upstream failures still resolves the job to
    success — closes only via a live dogfood run in production CI. Here we
    assert the structural absence of a hard failure exit anywhere in the gate.
    """
    raw = _raw_text()
    assert not re.search(r"\bexit\s+1\b", raw), (
        "No step in the intake gate may `exit 1` — every failure path must "
        "fail open (exit 0), never block or delay the human arming decision"
    )


# ---------------------------------------------------------------------------
# Same-family misconfiguration guard — mirrors the review gate's own guard.
# ---------------------------------------------------------------------------


def test_same_family_misconfiguration_guard_compares_reviewer_family_against_claude() -> None:
    raw = _raw_text()
    assert _mentions_near(raw, "reviewer_family", "claude") or _mentions_near(
        raw, "misconfigured", "claude"
    ), (
        "The intake gate must compare the resolved reviewer family against "
        "the fixer's own family ('claude') to detect a same-family "
        "misconfiguration — a bare unrelated mention of 'claude' is not "
        "enough"
    )


def test_same_family_misconfiguration_labels_distinctly_and_never_runs_a_review() -> None:
    raw = _raw_text()
    assert "intake-assessment:misconfigured" in raw, (
        "A same-family misconfiguration must apply the distinct "
        "`intake-assessment:misconfigured` label — never a silent fallback "
        "to a same-family self-assessment"
    )


# ---------------------------------------------------------------------------
# Supply-chain pinning
# ---------------------------------------------------------------------------


def test_every_uses_reference_is_sha_pinned() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    assert refs, "Intake gate must contain at least one `uses:` step (e.g. checkout)"
    for ref in refs:
        assert "@" in ref, f"`uses: {ref}` must pin a ref via '@<sha>'"
        pinned_ref = ref.rsplit("@", 1)[1]
        assert SHA_PIN_PATTERN.match(pinned_ref), (
            f"`uses: {ref}` must be pinned to a full 40-hex-char commit SHA, "
            f"not a mutable tag or branch (got {pinned_ref!r})"
        )


def test_checkout_and_setup_uv_pin_the_same_commits_used_repo_wide() -> None:
    raw = _raw_text()
    assert CHECKOUT_PIN in raw, (
        f"`actions/checkout` must be pinned to the same commit used "
        f"everywhere else in this repo ({CHECKOUT_PIN}), not merely any "
        "40-hex SHA — a stale/wrong commit introduced during copy-paste "
        "must be caught"
    )
    assert SETUP_UV_PIN in raw, (
        f"`astral-sh/setup-uv` must be pinned to the same commit used "
        f"everywhere else in this repo ({SETUP_UV_PIN})"
    )


# ---------------------------------------------------------------------------
# Banned patterns
# ---------------------------------------------------------------------------


def test_never_triggers_on_pull_request_target() -> None:
    raw = _raw_text()
    assert "pull_request_target" not in raw, (
        "`pull_request_target` must never appear anywhere in the intake gate"
    )


def test_never_references_track_progress() -> None:
    raw = _raw_text()
    assert "track_progress" not in raw, "`track_progress` must never appear in the intake gate"


# ---------------------------------------------------------------------------
# Issue body/title as DATA — non-agent fetch, read before the model is invoked
# ---------------------------------------------------------------------------


def test_non_agent_fetch_issue_as_data_step_exists_before_the_cursor_invocation() -> None:
    steps = _all_steps(_parsed())

    def _writes_issue_data_file(step: dict) -> bool:
        return "uses" not in step and bool(re.search(r"tmp/issue", step.get("run") or ""))

    def _invokes_cursor(step: dict) -> bool:
        return bool(re.search(r"agent\s+-p\b", step.get("run") or ""))

    fetch_idx = next((i for i, step in enumerate(steps) if _writes_issue_data_file(step)), None)
    invoke_idx = next((i for i, step in enumerate(steps) if _invokes_cursor(step)), None)

    assert fetch_idx is not None, (
        "A plain shell step must fetch and sanitize the issue title/body, "
        "writing it to a `tmp/issue*` file for the agent to read as DATA — "
        "never an agent action, never interpolated directly into a prompt"
    )
    assert invoke_idx is not None, (
        "Expected a Cursor CLI invocation step (`agent -p ...`) somewhere in the job"
    )
    assert fetch_idx < invoke_idx, (
        "The non-agent issue-fetch step must run BEFORE the Cursor "
        "invocation — the model reads the issue as an already-written file, "
        "never as a live/trusted instruction stream"
    )


# ---------------------------------------------------------------------------
# Cursor invocation shape — mirrors the review hub's reused mechanics
# ---------------------------------------------------------------------------


def test_cursor_invocation_mirrors_the_reused_review_hub_mechanics() -> None:
    raw = _raw_text()
    assert "--output-format json" in raw, (
        "The Cursor invocation must request `--output-format json`"
    )
    assert "--force" in raw, (
        "The Cursor invocation must pass `--force` to bypass the "
        "workspace-trust prompt in the TTY-less CI runner"
    )
    assert re.search(r"--model\s+\S+", raw), "The Cursor invocation must pass `--model <resolved>`"
    assert "--api-key" in raw, "The Cursor invocation must pass `--api-key`"
    assert "continue-on-error: true" in raw, (
        "The Cursor invocation step must declare `continue-on-error: true` "
        "so a non-zero Cursor exit does not fail the job before the "
        "fail-open owner runs"
    )
    assert "timeout-minutes" in raw, (
        "The intake gate must declare `timeout-minutes` somewhere — cost is "
        "bounded by job/step timeout since no native Cursor CLI turn cap "
        "exists"
    )


# ---------------------------------------------------------------------------
# Idempotency — re-labeling an already-assessed issue must not double-post
# ---------------------------------------------------------------------------


def test_idempotency_guard_step_exists_and_skips_when_already_assessed() -> None:
    """Structural proxy: this checks the guard's presence via the same
    'idempotent' vocabulary `issue-autofix.yml` uses for its own already-triaged
    skip step, not the exact mechanism (comment-search vs label-search is an
    implementer choice).
    """
    raw = _raw_text()
    assert re.search(r"idempotent", raw, re.IGNORECASE), (
        "An idempotency-guard step must exist and skip the run when an "
        "intake-assessment comment/label already exists on the issue — "
        "re-labeling an already-assessed issue must never post a second "
        "assessment comment"
    )
