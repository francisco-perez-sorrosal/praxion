"""Publication invariants for the scheduled sentinel workflow.

Split from `test_sentinel_workflow_invariants.py`, which keeps the envelope's
structural invariants and the parsing helpers imported here. This module holds
what a report's publication depends on: publication gated on a clear credential
gate, the token families the gate matches, closed grant and settings flags, no
cache saved after the agent runs, step outputs passed through `env:` only, the
checkout ref, and the state patch reaching the artifact.
"""

from __future__ import annotations

import copy
import re

import pytest
from test_sentinel_workflow_invariants import (  # bare name: sibling test module
    KILL_SWITCH_FLAGS,
    _action_steps,
    _all_steps,
    _claude_args_blocks,
    _parsed,
    _settings_json,
)


@pytest.mark.parametrize(
    "token",
    [
        "sk-ant-api03-" + "A" * 40,
        "ghp_" + "B" * 36,
        "ghs_" + "C" * 36,
        "github_pat_" + "D" * 22 + "_" + "E" * 59,
    ],
    ids=["anthropic", "github_classic", "github_app", "github_fine_grained"],
)
def test_credential_gate_pattern_matches_each_token_family(token: str) -> None:
    gate = next(s for s in _all_steps(_parsed()) if s.get("id") == "credential_gate")
    match = re.search(r"grep -Ec -- '([^']+)'", gate.get("run") or "")
    assert match, "The credential gate must scan with `grep -Ec -- '<pattern>'`"
    assert re.search(match.group(1), token), (
        f"The credential gate's pattern misses a {token[:12]}… token — it would "
        "publish that secret in the public artifact"
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
# Mutation canaries — one per publication invariant a single edit could break.
# ---------------------------------------------------------------------------


PUBLICATION_CANARIES = [
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


@pytest.mark.parametrize(("mutate", "predicate"), PUBLICATION_CANARIES)
def test_publication_canary_bites_on_a_known_bad_workflow(mutate, predicate) -> None:
    mutated = mutate(_parsed())
    with pytest.raises(AssertionError):
        predicate(mutated)
