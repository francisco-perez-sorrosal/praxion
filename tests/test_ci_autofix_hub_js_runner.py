"""Structural invariants for the ci-autofix hub's JS/TS test-runner grant.

Covers the policy-gated runner selector: the `classify` job's
`js_install_cmd`/`js_test_grant` outputs, the enum's safe default-off, the
closed-table mapping that keeps a free-form policy string out of the agent
allowlist, and the append-only wiring of the grant token onto the fixer's
`--allowedTools` line.

The package-manager detection that feeds `js_install_cmd`, and the install
step's own robustness contract, live in `test_ci_autofix_hub_pm_install.py`.

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


def _allowed_tools_value(step: dict) -> str | None:
    """Extract the quoted value of `--allowedTools "..."` from a step's `claude_args`."""
    match = re.search(r'--allowedTools "([^"]*)"', _claude_args(step))
    return match.group(1) if match else None


def _classify_step(job: dict) -> dict | None:
    """Return the `classify` job's `id: classify` step, or `None` if absent."""
    return next((step for step in job.get("steps") or [] if step.get("id") == "classify"), None)


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
    assert "pnpm install" not in allowed_tools, (
        "The fixer allowlist must never grant `pnpm install`"
    )


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
    assert value is not None, (
        'Expected an --allowedTools "..." value in the fixer step\'s claude_args'
    )
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
    assert value is not None, (
        'Expected an --allowedTools "..." value in the fixer step\'s claude_args'
    )
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
