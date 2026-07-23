"""Structural invariant tests for the cross-model review hub reusable workflow.

`.github/workflows/reusable-cross-model-review.yml` does not exist yet — these
tests define the security/interface contract the implementer must satisfy
when building it as the peer of the shipped `reusable-ci-autofix.yml`, but
with an inverted privilege profile: the fixer writes, the reviewer only
reads-and-annotates. Every test reads the file lazily (inside the function
body, not at module import time) so collection succeeds before the file
exists; running this module now is expected to fail — the first test with a
clear "file not found" assertion, the rest with an uncaught FileNotFoundError
raised while reading a file that is not there yet — but never with an import
error at collection time.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps, permission grants, and banned patterns. It cannot
verify runtime behavior (what a real Cursor CLI invocation actually returns,
whether every combination of upstream failures truly resolves the job to
success, whether the live `--list-models`/`--output-format json` envelope
shapes match what is assumed here). Where a test is a structural proxy for a
runtime guarantee, its docstring says so explicitly — those guarantees close
only via a live dogfood run in production CI, once a real Cursor round-trip
is exercised end to end.

Build note: this module also intentionally accumulates from a mostly-RED
state as the hub is built sub-step-by-sub-step across a same-file build
sequence (skeleton → model resolution → diff fetch → review/parse → act →
fail-open wrapper) — full GREEN is only expected once every mechanism lands,
not after any single sub-step.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HUB_WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "reusable-cross-model-review.yml"

SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MODEL_FLAG_PATTERN = re.compile(r"--model\s+(\S+)")


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


def _mentions_default_near(raw: str, field: str, window: int = 400) -> bool:
    """True if `field` and a "default" marker co-occur within `window` chars, either order."""
    return _mentions_near(raw, field, "default", window)


# ---------------------------------------------------------------------------
# Existence and parseability
# ---------------------------------------------------------------------------


def test_hub_workflow_file_exists_and_parses_as_yaml() -> None:
    assert HUB_WORKFLOW_FILE.exists(), (
        f"{HUB_WORKFLOW_FILE} not found. The implementer must create the "
        "cross-model review hub as the peer of reusable-ci-autofix.yml."
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
        "on.workflow_call.inputs must declare `policy_path` — the caller's "
        "per-repo policy file location must be sourced through the "
        "interface, never hardcoded"
    )
    assert (
        inputs["policy_path"].get("default") == ".github/autofix-policy.yml"
    ), "`policy_path` input must default to '.github/autofix-policy.yml'"


def test_workflow_call_declares_required_cursor_api_key_secret() -> None:
    parsed = _parsed()
    workflow_call = _on_block(parsed)["workflow_call"]
    secrets_block = workflow_call.get("secrets", {}) or {}
    assert (
        "CURSOR_API_KEY" in secrets_block
    ), "on.workflow_call.secrets must explicitly declare CURSOR_API_KEY"
    assert secrets_block["CURSOR_API_KEY"].get("required") is True, (
        "CURSOR_API_KEY must be declared `required: true` — a caller invoking "
        "the hub without this secret must fail loudly, not silently"
    )


def test_never_uses_secrets_inherit() -> None:
    raw = _raw_text()
    assert "secrets: inherit" not in raw, (
        "`secrets: inherit` must never appear anywhere in the hub — it "
        "silently no-ops cross-org auth; CURSOR_API_KEY must be passed by "
        "explicit mapping only"
    )


# ---------------------------------------------------------------------------
# Banned patterns
# ---------------------------------------------------------------------------


def test_never_references_track_progress() -> None:
    raw = _raw_text()
    assert "track_progress" not in raw, "`track_progress` must never appear in the hub"


def test_never_triggers_on_pull_request_target() -> None:
    raw = _raw_text()
    assert (
        "pull_request_target" not in raw
    ), "`pull_request_target` must never appear anywhere in the hub"


def test_never_uses_force_or_yolo_flag() -> None:
    """Non-generativity is enforced by permission scope (see the
    `test_no_job_grants_*` tests below), not by a CLI flag. `--force`/
    `--yolo` would enable unconfirmed file edits in a gate that must never
    edit, so neither flag may appear anywhere in the hub.
    """
    raw = _raw_text()
    assert "--force" not in raw, "`--force` must never appear in the hub"
    assert "--yolo" not in raw, "`--yolo` must never appear in the hub"


# ---------------------------------------------------------------------------
# Supply-chain pinning
# ---------------------------------------------------------------------------


def test_every_uses_reference_is_sha_pinned() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    assert refs, "Hub workflow must contain at least one `uses:` step (e.g. checkout)"
    for ref in refs:
        assert "@" in ref, f"`uses: {ref}` must pin a ref via '@<sha>'"
        pinned_ref = ref.rsplit("@", 1)[1]
        assert SHA_PIN_PATTERN.match(pinned_ref), (
            f"`uses: {ref}` must be pinned to a full 40-hex-char commit SHA, "
            f"not a mutable tag or branch (got {pinned_ref!r})"
        )


# ---------------------------------------------------------------------------
# Structural non-generativity — the load-bearing invariant this whole hub
# exists to guarantee. A reviewer job that can write repository contents (or
# mint an OIDC token) would collapse the entire non-generative role-split
# this design depends on, so this invariant gets triple coverage: an exact
# permission-dict match, and two standalone regression guards, so that any
# later same-file build step that accidentally widens the grant fails loudly
# and specifically.
# ---------------------------------------------------------------------------


def test_review_job_permissions_are_exactly_pull_requests_write_and_contents_read() -> None:
    parsed = _parsed()
    permissions = _job_permissions(parsed)
    assert permissions, "Hub workflow must declare at least one job with its own `permissions:`"
    assert any(perm == {"pull-requests": "write", "contents": "read"} for perm in permissions), (
        "The review job's own `permissions:` must grant EXACTLY "
        "`pull-requests: write` + `contents: read` — no more, no less"
    )


def test_no_job_grants_contents_write() -> None:
    parsed = _parsed()
    for perm in _job_permissions(parsed):
        assert perm.get("contents") != "write", (
            "No job in the cross-model review hub may hold `contents: write` "
            "— the reviewer must never be able to alter repository content"
        )


def test_no_job_grants_id_token_write() -> None:
    parsed = _parsed()
    for perm in _job_permissions(parsed):
        assert "id-token" not in perm, (
            "No job in the cross-model review hub may hold `id-token: write` "
            "— OIDC-exchange capability belongs to the fixer hub only, never "
            "the read-only reviewer"
        )


def test_no_git_write_or_pr_create_step_exists() -> None:
    parsed = _parsed()
    for step in _all_steps(parsed):
        run = step.get("run") or ""
        assert "git commit" not in run, "The review job must never run `git commit`"
        assert "git push" not in run, "The review job must never run `git push`"
        assert "gh pr create" not in run, "The review job must never run `gh pr create`"


# ---------------------------------------------------------------------------
# Gate decision + fail-safe policy parsing
# ---------------------------------------------------------------------------


def test_gate_decision_reads_cross_model_gate_policy_value() -> None:
    raw = _raw_text()
    assert (
        "cross_model_gate" in raw
    ), "The gate decision must read `review.cross_model_gate` from the caller's policy"


def test_gate_decision_recognizes_both_agent_authored_branch_prefixes() -> None:
    raw = _raw_text()
    assert (
        "ci-autofix/" in raw
    ), "The gate must recognize the ci-autofix/ branch prefix when scoping to agent-authored PRs"
    assert "issue-autofix/" in raw, (
        "The gate must recognize the issue-autofix/ branch prefix when "
        "scoping to agent-authored PRs"
    )


def test_missing_or_malformed_policy_falls_back_to_a_safe_gate_default() -> None:
    """Structural proxy for fail-safe policy handling — see the module
    docstring for what real runtime behavior this cannot verify.
    """
    raw = _raw_text()
    assert _mentions_default_near(raw, "cross_model_gate"), (
        "A missing/malformed policy must not silently disable or widen the "
        "gate — a safe default must be defined near cross_model_gate"
    )


def test_missing_or_malformed_policy_falls_back_to_a_safe_reviewer_family() -> None:
    """Structural proxy — see test_missing_or_malformed_policy_falls_back_to_a_safe_gate_default."""
    raw = _raw_text()
    assert _mentions_default_near(raw, "reviewer_family"), (
        "A missing/malformed policy must not leave reviewer_family "
        "undefined — a safe default must be defined near reviewer_family"
    )


# ---------------------------------------------------------------------------
# Model resolution — live, never hardcoded, never same-family
# ---------------------------------------------------------------------------


def test_model_resolution_queries_list_models_live() -> None:
    raw = _raw_text()
    assert "--list-models" in raw, (
        "The hub must resolve the reviewer model live via `agent "
        "--list-models` — never a hardcoded model catalogue"
    )


def test_model_flag_is_populated_from_a_resolved_variable_never_a_literal_id() -> None:
    raw = _raw_text()
    matches = MODEL_FLAG_PATTERN.findall(raw)
    assert matches, "Expected at least one `--model <value>` invocation of the Cursor CLI"
    for token in matches:
        assert "$" in token, (
            f"`--model {token}` must be populated from a resolved shell/step "
            "variable, never a hardcoded model id literal"
        )


def test_misconfigured_reviewer_family_is_compared_against_the_fixer_family() -> None:
    raw = _raw_text()
    assert _mentions_near(raw, "reviewer_family", "claude") or _mentions_near(
        raw, "misconfigured", "claude"
    ), (
        "The hub must compare the resolved reviewer family against the "
        "fixer's own family ('claude') to detect a same-family "
        "misconfiguration — a bare unrelated mention of 'claude' is not enough"
    )


def test_misconfigured_branch_labels_distinctly() -> None:
    raw = _raw_text()
    assert "cross-model-review:misconfigured" in raw, (
        "A same-family misconfiguration must apply the distinct "
        "`cross-model-review:misconfigured` label — never a silent "
        "fallback to a same-family review"
    )


# ---------------------------------------------------------------------------
# Diff/PR-body as DATA (non-agent fetch, sanitized, framed as untrusted)
# ---------------------------------------------------------------------------


def test_diff_fetch_step_is_non_agent() -> None:
    parsed = _parsed()
    fetch_steps = [step for step in _all_steps(parsed) if "gh pr diff" in (step.get("run") or "")]
    assert fetch_steps, (
        "A plain shell step must fetch the PR diff via `gh pr diff` (or "
        "equivalent), not an agent action"
    )
    for step in fetch_steps:
        assert "uses" not in step, (
            "The diff-fetch step must be a `run:` step, not a `uses:` agent "
            "action — the diff is written to a file for the reviewer to read "
            "as DATA, never interpolated into its instructions"
        )


def test_pr_body_is_fetched_as_data_too() -> None:
    raw = _raw_text()
    assert "gh pr view" in raw, (
        "The fixer PR's title/body must be fetched (e.g. via `gh pr view`) "
        "alongside the diff, as additional reviewer context"
    )


def test_diff_output_is_sanitized_before_the_reviewer_reads_it() -> None:
    """Structural proxy: asserts sanitization is documented OR mechanically
    performed somewhere in the workflow — the exact mechanism is an
    implementer choice.
    """
    raw = _raw_text()
    assert re.search(r"saniti|truncat|\\x1b|cut -c|head -c|strip", raw, re.IGNORECASE), (
        "The fetched diff/PR-body content must be sanitized (e.g. ANSI-escape "
        "stripped, truncated) before the reviewer reads it as data"
    )


def test_review_prompt_frames_diff_and_pr_body_as_untrusted_data() -> None:
    raw = _raw_text()
    assert re.search(r"untrusted", raw, re.IGNORECASE), (
        "The reviewer-facing prompt must explicitly frame the fetched diff + "
        "PR body as untrusted DATA (prompt-injection mitigation)"
    )
    assert re.search(r"instruction", raw, re.IGNORECASE), (
        "The reviewer-facing prompt must explicitly distinguish diff/PR-body "
        "content from instructions (prompt-injection mitigation)"
    )


def test_review_prompt_forbids_a_rewritten_fix() -> None:
    raw = _raw_text().lower()
    assert "rewritten fix" in raw, (
        "The reviewer prompt must reference 'a rewritten fix' as the "
        "explicit thing it must never propose"
    )
    assert re.search(
        r"do not|never|not propose", raw
    ), "The 'rewritten fix' reference must be an explicit negation, not merely descriptive text"


def test_review_prompt_demands_a_structured_json_verdict() -> None:
    raw = _raw_text()
    assert (
        "verdict" in raw
    ), "The reviewer prompt must demand a JSON verdict object with a `verdict` key"
    assert (
        "findings" in raw
    ), "The reviewer prompt must demand a JSON verdict object with a `findings` key"
    assert "approve" in raw, (
        "The verdict's `approve` value must appear in the hub (prompt text "
        "and/or act-step branching)"
    )
    assert "request-changes" in raw, (
        "The verdict's `request-changes` value must appear in the hub "
        "(prompt text and/or act-step branching)"
    )


# ---------------------------------------------------------------------------
# Act — labels, comment, draft toggle; never close, never counter-fix
# ---------------------------------------------------------------------------


def test_approve_verdict_applies_approved_and_reviewed_by_labels() -> None:
    raw = _raw_text()
    assert (
        "cross-model-review:approved" in raw
    ), "An `approve` verdict must apply the `cross-model-review:approved` label"
    assert "reviewed-by:" in raw, (
        "Every verdict outcome must apply a `reviewed-by:<family>` label "
        "naming the reviewing model family (audit trail)"
    )


def test_request_changes_verdict_applies_changes_requested_label_and_marks_draft() -> None:
    raw = _raw_text()
    assert (
        "cross-model-review:changes-requested" in raw
    ), "A `request-changes` verdict must apply the `cross-model-review:changes-requested` label"
    assert (
        "gh pr ready" in raw
    ), "A `request-changes` verdict must call `gh pr ready` to toggle draft state"
    assert (
        "--undo" in raw
    ), "The draft toggle must use `--undo` (mark as draft), not the default (mark ready)"


def test_request_changes_never_closes_or_commits() -> None:
    raw = _raw_text()
    assert "gh pr close" not in raw, "The review job must never close a PR"
    assert "git commit" not in raw, "The review job must never commit a counter-fix"
    assert "git push" not in raw, "The review job must never push a counter-fix"


# ---------------------------------------------------------------------------
# Fail-open — every failure path converges on `unavailable`, exit 0
# ---------------------------------------------------------------------------


def test_fail_open_applies_unavailable_label() -> None:
    raw = _raw_text()
    assert "cross-model-review:unavailable" in raw, (
        "Every fail-open path (non-zero exit, timeout, unparseable verdict, "
        "no model of the requested family) must converge on the "
        "`cross-model-review:unavailable` label"
    )


def test_no_failure_path_exits_non_zero() -> None:
    """Structural proxy for the fail-open guarantee: real runtime behavior —
    that every combination of upstream failures still resolves the job to
    success — closes only via a live dogfood run in production CI. Here we
    assert the structural absence of a hard failure exit anywhere in the hub.
    """
    raw = _raw_text()
    assert not re.search(r"\bexit\s+1\b", raw), (
        "No step in the cross-model review hub may `exit 1` — every failure "
        "path must fail open (exit 0), never block the fix pipeline"
    )


def test_timeout_minutes_is_declared_on_a_job() -> None:
    parsed = _parsed()
    jobs = _jobs(parsed)
    assert jobs, "Hub workflow must declare at least one job"
    assert any("timeout-minutes" in job for job in jobs.values()), (
        "The review job must declare `timeout-minutes` — cost is bounded by "
        "job timeout since no native Cursor CLI turn cap exists"
    )
