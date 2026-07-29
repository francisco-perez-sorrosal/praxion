"""Structural invariant tests for the label-taxonomy reconciler's hub,
Praxion's own caller, and the fleet-distributed templates.

None of the four target files exist yet:
  - `.github/workflows/reusable-labels-reconcile.yml` (hub)
  - `.github/workflows/labels-reconcile.yml` (Praxion's own thin caller)
  - `claude/project-baseline/labels/labels-reconcile.yml.tmpl` (fleet caller template)
  - `claude/project-baseline/labels/labels.yml.tmpl` (fleet manifest template)

Every test reads its target file lazily (inside the function body, not at
module import time) so collection succeeds before any of these files exist;
running this module now is expected to fail with a clear "file not found" (or,
for the manifest-template/Praxion-manifest comparison, a missing-key)
assertion for every test — RED, never a collection or import error.

This suite is the single most security-load-bearing test file in this
pipeline: it structurally proves the new privileged hub (`issues: write`)
can never widen its own permission ceiling beyond `{issues: write, contents:
read}`, is triggerable only via `workflow_call`, and can never reach the
issue/PR label-*application* endpoint (`gh issue`/`gh pr`) — preserving the
`ecosystem-feedback` human-only arming invariant (dec-281) by construction.

Scope note: this suite verifies structure — parsed YAML shape and raw-text
regex/grep presence of required (or forbidden) invocations. It cannot verify
runtime behavior (e.g. that a live `gh label create --force` run against a
repo missing labels is actually idempotent) — that closes via dogfooding
once Praxion's own caller exercises the hub in production CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HUB_WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "reusable-labels-reconcile.yml"
CALLER_WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "labels-reconcile.yml"
FLEET_CALLER_TEMPLATE_FILE = (
    PROJECT_ROOT / "claude" / "project-baseline" / "labels" / "labels-reconcile.yml.tmpl"
)
FLEET_MANIFEST_TEMPLATE_FILE = (
    PROJECT_ROOT / "claude" / "project-baseline" / "labels" / "labels.yml.tmpl"
)
PRAXION_MANIFEST_FILE = PROJECT_ROOT / ".github" / "labels.yml"

EXPECTED_JOB_PERMISSIONS = {"issues": "write", "contents": "read"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_text(path: Path) -> str:
    """Return a file's raw content (read lazily so collection succeeds)."""
    return path.read_text(encoding="utf-8")


def _parsed(path: Path) -> dict:
    """Parse a file as YAML (read lazily so collection succeeds)."""
    return yaml.safe_load(_raw_text(path))


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


def _single_job(parsed: dict) -> dict:
    """Return the sole job body from a workflow document."""
    jobs = parsed.get("jobs") or {}
    assert jobs, "Workflow must declare at least one job"
    return next(iter(jobs.values()))


# ---------------------------------------------------------------------------
# Hub: existence and parseability
# ---------------------------------------------------------------------------


def test_hub_workflow_file_exists_and_parses_as_yaml() -> None:
    assert HUB_WORKFLOW_FILE.exists(), (
        f"{HUB_WORKFLOW_FILE} not found. The implementer must create the "
        "reconciler hub reusable workflow."
    )
    parsed = _parsed(HUB_WORKFLOW_FILE)
    assert isinstance(parsed, dict), "Hub workflow must parse to a YAML mapping"


# ---------------------------------------------------------------------------
# Hub: workflow_call-only trigger, manifest_path input, no secrets
# ---------------------------------------------------------------------------


def test_hub_on_block_declares_only_the_workflow_call_trigger() -> None:
    parsed = _parsed(HUB_WORKFLOW_FILE)
    on_block = _on_block(parsed)
    assert set(on_block.keys()) == {"workflow_call"}, (
        "Hub `on:` block must declare `workflow_call` only — no `push`, "
        "`pull_request`, `schedule`, or any other trigger — so the hub is "
        "un-triggerable except through a caller; got trigger keys "
        f"{sorted(on_block.keys(), key=str)}"
    )


def test_hub_workflow_call_declares_manifest_path_input_with_safe_default() -> None:
    parsed = _parsed(HUB_WORKFLOW_FILE)
    workflow_call = _on_block(parsed)["workflow_call"] or {}
    inputs = workflow_call.get("inputs") or {}
    assert "manifest_path" in inputs, (
        "on.workflow_call.inputs must declare `manifest_path` — the caller's "
        "per-repo manifest location must be sourced through the interface, "
        "never hardcoded"
    )
    manifest_path = inputs["manifest_path"]
    assert manifest_path.get("type") == "string", "`manifest_path` input must be type `string`"
    assert manifest_path.get("required") is False, "`manifest_path` input must be `required: false`"
    assert (
        manifest_path.get("default") == ".github/labels.yml"
    ), "`manifest_path` input must default to '.github/labels.yml'"


def test_hub_workflow_call_declares_no_secrets_block() -> None:
    parsed = _parsed(HUB_WORKFLOW_FILE)
    workflow_call = _on_block(parsed)["workflow_call"] or {}
    assert "secrets" not in workflow_call, (
        "Hub must declare no `secrets:` mapping under `workflow_call` — the "
        "reconciler uses the built-in GITHUB_TOKEN only, unlike the two "
        "agent-driven hubs which require an external OAuth/API-key secret"
    )


# ---------------------------------------------------------------------------
# Hub: least-privilege permission ceiling
# ---------------------------------------------------------------------------


def test_hub_declares_top_level_permissions_empty() -> None:
    parsed = _parsed(HUB_WORKFLOW_FILE)
    assert parsed.get("permissions") == {}, (
        "Hub's top-level `permissions:` must be the empty mapping "
        "(deny-by-default); only the job below should raise the ceiling"
    )


def test_hub_single_job_permissions_are_exactly_issues_write_and_contents_read() -> None:
    parsed = _parsed(HUB_WORKFLOW_FILE)
    job = _single_job(parsed)
    assert job.get("permissions") == EXPECTED_JOB_PERMISSIONS, (
        f"Hub job permissions must be EXACTLY {EXPECTED_JOB_PERMISSIONS} — no "
        f"more, no less (e.g. no `contents: write`, no `pull-requests: *`) — "
        f"got {job.get('permissions')!r}"
    )


# ---------------------------------------------------------------------------
# Additive-only / `ecosystem-feedback`-unreachable invariant (dec-281)
# ---------------------------------------------------------------------------


def test_hub_never_calls_gh_issue_or_gh_pr() -> None:
    raw = _raw_text(HUB_WORKFLOW_FILE)
    assert not re.search(r"gh issue\b", raw), (
        "Hub must never call `gh issue ...` — any issue-label-application "
        "invocation would let the reconciler reach the endpoint the "
        "`ecosystem-feedback` human-only arming invariant (dec-281) forbids"
    )
    assert not re.search(r"gh pr\b", raw), (
        "Hub must never call `gh pr ...` — any PR-label-application "
        "invocation would let the reconciler reach the endpoint the "
        "`ecosystem-feedback` human-only arming invariant (dec-281) forbids"
    )


def test_hub_only_gh_label_subcommand_present_is_create() -> None:
    raw = _raw_text(HUB_WORKFLOW_FILE)
    subcommands = set(re.findall(r"gh label (\w+)", raw))
    assert subcommands == {"create"}, (
        "The hub must invoke only `gh label create` — never `gh label "
        f"delete` or any other `gh label` subcommand; found {subcommands!r}"
    )


def test_hub_every_gh_label_create_invocation_passes_force() -> None:
    raw = _raw_text(HUB_WORKFLOW_FILE)
    create_calls = re.findall(r"gh label create[^\n]*", raw)
    assert create_calls, "Expected at least one `gh label create` invocation in the hub"
    for call in create_calls:
        assert "--force" in call, (
            f"Every `gh label create` invocation must pass `--force` (idempotent "
            f"create-or-update) — offending line: {call!r}"
        )


def test_hub_reconcile_loop_concatenates_baseline_and_additional() -> None:
    raw = _raw_text(HUB_WORKFLOW_FILE)
    assert re.search(
        r'manifest\.get\(\s*["\']baseline["\']', raw
    ), "The reconcile loop must read the manifest's `baseline:` block"
    assert re.search(
        r'manifest\.get\(\s*["\']additional["\']', raw
    ), "The reconcile loop must read the manifest's `additional:` block"
    assert re.search(
        r'manifest\.get\(\s*["\']baseline["\'][^\n]*\+[^\n]*manifest\.get\(\s*["\']additional["\']',
        raw,
    ), (
        "baseline: and additional: must be concatenated into ONE entry list — "
        "a project's additional: labels must reconcile alongside the shipped "
        "baseline, not be read and silently discarded"
    )


# ---------------------------------------------------------------------------
# Praxion's own thin caller — existence and trigger
# ---------------------------------------------------------------------------


def test_caller_workflow_file_exists_and_parses_as_yaml() -> None:
    assert CALLER_WORKFLOW_FILE.exists(), (
        f"{CALLER_WORKFLOW_FILE} not found. The implementer must create "
        "Praxion's own thin caller of the reconciler hub."
    )
    parsed = _parsed(CALLER_WORKFLOW_FILE)
    assert isinstance(parsed, dict), "Caller workflow must parse to a YAML mapping"


def test_caller_on_block_includes_push_scoped_to_the_manifest_path_on_main() -> None:
    parsed = _parsed(CALLER_WORKFLOW_FILE)
    on_block = _on_block(parsed)
    assert "push" in on_block, (
        "Caller must trigger on `push` so committing the manifest reconciles "
        "labels automatically, without a manual step"
    )
    push_block = on_block["push"] or {}
    assert push_block.get("branches") == ["main"], (
        "Caller's `push` trigger must be scoped to the default branch "
        f"(['main']) — got {push_block.get('branches')!r}"
    )
    assert push_block.get("paths") == [".github/labels.yml"], (
        "Caller's `push` trigger must be scoped to the manifest path via a "
        f"`paths:` filter — got {push_block.get('paths')!r}"
    )


def test_caller_on_block_includes_workflow_dispatch() -> None:
    parsed = _parsed(CALLER_WORKFLOW_FILE)
    on_block = _on_block(parsed)
    assert (
        "workflow_dispatch" in on_block
    ), "Caller must also support manual `workflow_dispatch` invocation"


# ---------------------------------------------------------------------------
# Praxion's own thin caller — same-repo local ref + permission ceiling
# ---------------------------------------------------------------------------


def test_caller_uses_the_same_repo_local_ref_never_a_cross_repo_pin() -> None:
    parsed = _parsed(CALLER_WORKFLOW_FILE)
    job = _single_job(parsed)
    assert job.get("uses") == "./.github/workflows/reusable-labels-reconcile.yml", (
        "Praxion's own caller (#1) must invoke the hub via a same-repo local "
        "`./...` ref (tracks HEAD) — never a cross-repo SHA pin, which is "
        f"reserved for managed callers — got {job.get('uses')!r}"
    )


def test_caller_declares_top_level_permissions_empty() -> None:
    parsed = _parsed(CALLER_WORKFLOW_FILE)
    assert parsed.get("permissions") == {}, (
        "Caller's top-level `permissions:` must be the empty mapping "
        "(deny-by-default); only the job below should raise the ceiling"
    )


def test_caller_job_permissions_redeclare_exactly_issues_write_and_contents_read() -> None:
    parsed = _parsed(CALLER_WORKFLOW_FILE)
    job = _single_job(parsed)
    assert job.get("permissions") == EXPECTED_JOB_PERMISSIONS, (
        f"Caller's job permissions must re-declare EXACTLY {EXPECTED_JOB_PERMISSIONS} "
        "— GitHub caps the hub's effective token at the caller's own grant, so "
        f"an under- or over-scoped caller breaks the ceiling — got {job.get('permissions')!r}"
    )


# ---------------------------------------------------------------------------
# Fleet caller template — SHA-pin schema
# ---------------------------------------------------------------------------


def test_fleet_caller_template_file_exists() -> None:
    assert FLEET_CALLER_TEMPLATE_FILE.exists(), (
        f"{FLEET_CALLER_TEMPLATE_FILE} not found. The implementer must create "
        "the fleet thin-caller template for managed-project installs."
    )


def test_fleet_caller_template_uses_line_matches_the_documented_placeholder_form_literally() -> (
    None
):
    raw = _raw_text(FLEET_CALLER_TEMPLATE_FILE)
    assert (
        "uses: {{PRAXION_HUB}}/.github/workflows/reusable-labels-reconcile.yml@{{HUB_SHA}}" in raw
    ), (
        "Fleet caller template's `uses:` line must match the literal "
        "unresolved placeholder form "
        "'{{PRAXION_HUB}}/.github/workflows/reusable-labels-reconcile.yml@{{HUB_SHA}}' "
        "— the same two placeholder tokens the two existing fleet templates use"
    )


def test_fleet_caller_template_contains_no_placeholder_other_than_praxion_hub_and_hub_sha() -> None:
    raw = _raw_text(FLEET_CALLER_TEMPLATE_FILE)
    tokens = set(re.findall(r"\{\{[A-Z0-9_]+\}\}", raw))
    assert tokens == {"{{PRAXION_HUB}}", "{{HUB_SHA}}"}, (
        "Fleet caller template must carry exactly the two documented "
        f"placeholders — found {tokens!r}"
    )


# ---------------------------------------------------------------------------
# Fleet manifest template — filled baseline, empty additional
# ---------------------------------------------------------------------------


def test_fleet_manifest_template_file_exists() -> None:
    assert FLEET_MANIFEST_TEMPLATE_FILE.exists(), (
        f"{FLEET_MANIFEST_TEMPLATE_FILE} not found. The implementer must "
        "create the fleet manifest template for managed-project installs."
    )


def test_fleet_manifest_template_baseline_matches_praxions_own_shipped_baseline() -> None:
    fleet_parsed = _parsed(FLEET_MANIFEST_TEMPLATE_FILE)
    fleet_baseline = fleet_parsed.get("baseline")
    assert fleet_baseline, "Fleet manifest template's `baseline:` block must be non-empty"
    praxion_parsed = _parsed(PRAXION_MANIFEST_FILE)
    assert fleet_baseline == praxion_parsed.get("baseline"), (
        "Fleet manifest template's `baseline:` must match Praxion's own "
        "shipped manifest baseline exactly — a managed project must start "
        "with the same taxonomy Praxion ships for itself"
    )


def test_fleet_manifest_template_additional_block_is_empty() -> None:
    fleet_parsed = _parsed(FLEET_MANIFEST_TEMPLATE_FILE)
    assert fleet_parsed.get("additional") == [], (
        "Fleet manifest template's `additional:` block must be the empty "
        "list — a freshly-installed project has no project-specific labels yet"
    )
