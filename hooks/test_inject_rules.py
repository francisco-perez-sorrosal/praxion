"""Tests for hooks/inject_rules.py — SessionStart rule-injection hook.

Verifies the eleven behavioral contracts:

  1. No project config → all 3 blacklistable rules in additionalContext output
  2. disable: [swe/_fixture-rule] → 2 rules in output, _fixture-rule absent
  3. disable: [ml/*] → glob resolves without crash; hook-deliver set unaffected
  4. disable: [swe/agent-behavioral-contract] → stderr warning; rule kept (core protection)
  5. disable: [swe/*] → warnings for core rules; non-core swe/* rules suppressed
  6. Malformed YAML project config → stderr log + fail open (all rules injected)
  7. version: 2 in project config → friendly stderr error + fail open (all rules injected)
  8. Missing manifest → stderr log + exit 0 (non-fatal)
  9. PRAXION_DISABLE_RULE_INJECTION=1 → exit 0, no additionalContext output
  10. Stderr summary line format validated
  11. Injection order: rules appear in manifest order (_fixture-rule → agent-model-routing
      → vcs/git-conventions)

Each test invokes the hook via ``subprocess.run``, setting:
  - ``CLAUDE_PLUGIN_ROOT`` env var → a temp dir containing a synthetic ``rules/_manifest.yaml``
  - ``cwd=<project_dir>`` → a temp dir optionally containing ``.claude/praxion-rules.yaml``

Tests are designed to fail (RED) before the production module exists and pass (GREEN)
once ``hooks/inject_rules.py`` is written.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = Path(__file__).resolve().parent / "inject_rules.py"

# ---------------------------------------------------------------------------
# Synthetic manifest content — mirrors the three hook-deliver rules from
# rules/_manifest.yaml.  Per the spec: manifest order is the injection order.
# ---------------------------------------------------------------------------

_FIXTURE_RULE_BODY = "## Fixture Rule\n\nThis is the test fixture rule body.\n"
_AGENT_MODEL_ROUTING_BODY = "## Agent Model Routing\n\nThis is the model routing rule body.\n"
_GIT_CONVENTIONS_BODY = "## Git Conventions\n\nThis is the git conventions rule body.\n"

# Core rule IDs the hook must refuse to suppress.
_CORE_IDS = [
    "swe/agent-behavioral-contract",
    "swe/swe-agent-coordination-protocol",
    "swe/agent-intermediate-documents",
    "swe/adr-conventions",
    "swe/adr-conventions-resident",
]

# Hook-deliver rule IDs (the three blacklistable always-loaded rules).
_HOOK_DELIVER_IDS = [
    "swe/_fixture-rule",
    "swe/agent-model-routing",
    "swe/vcs/git-conventions",
]


def _make_manifest(plugin_root: Path) -> None:
    """Write a synthetic rules/_manifest.yaml under plugin_root.

    Includes:
    - 5 core rules (install: symlink, core: true)
    - 3 hook-deliver rules with literal body content (install: hook-deliver, core: false)
    - 3 path-scoped ML rules (install: symlink, core: false, load: path_scoped)
      to validate that glob resolution against ml/* doesn't crash even though
      these rules are never in the hook-deliver set.
    - categories block with ml: and vcs: aliases
    """
    rules_dir = plugin_root / "rules"

    # Write the 3 hook-deliver rule body files so the hook can read them.
    (rules_dir / "swe").mkdir(parents=True, exist_ok=True)
    (rules_dir / "swe" / "vcs").mkdir(parents=True, exist_ok=True)
    (rules_dir / "swe" / "_fixture-rule.md").write_text(_FIXTURE_RULE_BODY, encoding="utf-8")
    (rules_dir / "swe" / "agent-model-routing.md").write_text(
        _AGENT_MODEL_ROUTING_BODY, encoding="utf-8"
    )
    (rules_dir / "swe" / "vcs" / "git-conventions.md").write_text(
        _GIT_CONVENTIONS_BODY, encoding="utf-8"
    )

    # Also write dummy bodies for core rules (hook reads them for core-rule text).
    core_files = {
        "swe/agent-behavioral-contract": "rules/swe/agent-behavioral-contract.md",
        "swe/swe-agent-coordination-protocol": "rules/swe/swe-agent-coordination-protocol.md",
        "swe/agent-intermediate-documents": "rules/swe/agent-intermediate-documents.md",
        "swe/adr-conventions": "rules/swe/adr-conventions.md",
        "swe/adr-conventions-resident": "rules/swe/adr-conventions-resident.md",
    }
    for rule_id, path in core_files.items():
        p = plugin_root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"## {rule_id} (core rule body)\n", encoding="utf-8")

    # ML path-scoped dummy files.
    (rules_dir / "ml").mkdir(parents=True, exist_ok=True)
    for ml_slug in (
        "eval-driven-verification",
        "experiment-tracking-conventions",
        "gpu-budget-conventions",
    ):
        (rules_dir / "ml" / f"{ml_slug}.md").write_text(
            f"## ML rule: {ml_slug}\n", encoding="utf-8"
        )

    # Build manifest YAML.
    manifest_lines = [
        "# AUTO-GENERATED synthetic test manifest",
        "version: 1",
        "generated_at: '2026-05-13T00:00:00Z'",
        "rules:",
    ]

    # Core rules.
    for rule_id in _CORE_IDS:
        rel_path = f"rules/{rule_id.replace('/', '/')}.md"
        manifest_lines += [
            f"- id: {rule_id}",
            f"  path: {rel_path}",
            "  load: always_on",
            "  core: true",
            "  install: symlink",
            "  chars: 1000",
        ]

    # Hook-deliver rules (in the spec's stable injection order).
    hook_deliver_specs = [
        ("swe/_fixture-rule", "rules/swe/_fixture-rule.md"),
        ("swe/agent-model-routing", "rules/swe/agent-model-routing.md"),
        ("swe/vcs/git-conventions", "rules/swe/vcs/git-conventions.md"),
    ]
    for rule_id, rel_path in hook_deliver_specs:
        manifest_lines += [
            f"- id: {rule_id}",
            f"  path: {rel_path}",
            "  load: always_on",
            "  core: false",
            "  install: hook-deliver",
            "  chars: 1000",
        ]

    # ML path-scoped rules (never in hook-deliver set; used to test ml/* glob).
    for ml_slug in (
        "eval-driven-verification",
        "experiment-tracking-conventions",
        "gpu-budget-conventions",
    ):
        manifest_lines += [
            f"- id: ml/{ml_slug}",
            f"  path: rules/ml/{ml_slug}.md",
            "  load: path_scoped",
            "  core: false",
            "  install: symlink",
            "  chars: 500",
        ]

    # Categories block.
    manifest_lines += [
        "categories:",
        "  ml:",
        "  - ml/eval-driven-verification",
        "  - ml/experiment-tracking-conventions",
        "  - ml/gpu-budget-conventions",
        "  writing:",
        "  - writing/aac-dac-conventions",
        "  vcs:",
        "  - swe/vcs/git-conventions",
        "  - swe/vcs/pr-conventions",
    ]

    (rules_dir / "_manifest.yaml").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")


def _hook_env(plugin_root: Path) -> dict[str, str]:
    """The environment a child hook process runs in.

    The mutation sensor sets MUTANT_UNDER_TEST for its own process; a child hook cannot locate
    mutmut's config from its cwd, so it must run the code as written.
    """
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(plugin_root)}
    env.pop("MUTANT_UNDER_TEST", None)
    return env


def _run_hook(
    plugin_root: Path,
    project_dir: Path,
    *,
    extra_env: dict[str, str] | None = None,
    timeout: int = 10,
) -> subprocess.CompletedProcess:
    """Invoke inject_rules.py as a subprocess.

    Sets CLAUDE_PLUGIN_ROOT to plugin_root and cwd to project_dir.
    Returns the CompletedProcess with captured stdout and stderr.
    Raises FileNotFoundError if the hook script does not yet exist (RED state).
    """
    env = {**_hook_env(plugin_root), **(extra_env or {})}
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=env,
        timeout=timeout,
    )


def _additional_context(result: subprocess.CompletedProcess) -> str:
    """Extract the additionalContext string from the hook's stdout JSON.

    Returns empty string if stdout is empty (no injection).
    Raises if stdout is non-empty but not valid JSON.
    """
    stdout = result.stdout.strip()
    if not stdout:
        return ""
    parsed = json.loads(stdout)
    # Two output shapes are acceptable:
    #   {"additionalContext": "..."}                  (flat)
    #   {"hookSpecificOutput": {"additionalContext": "..."}} (nested, matches banner hook)
    if "additionalContext" in parsed:
        return parsed["additionalContext"]
    hook_out = parsed.get("hookSpecificOutput", {})
    return hook_out.get("additionalContext", "")


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """A synthetic CLAUDE_PLUGIN_ROOT with a populated rules/_manifest.yaml."""
    _make_manifest(tmp_path)
    return tmp_path


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """An empty project directory (no .claude/praxion-rules.yaml)."""
    project = tmp_path / "project"
    project.mkdir()
    return project


# ---------------------------------------------------------------------------
# Helper: write a .claude/praxion-rules.yaml in the project directory
# ---------------------------------------------------------------------------


def _write_project_config(project_dir: Path, content: str) -> Path:
    """Write .claude/praxion-rules.yaml with the given YAML content."""
    dot_claude = project_dir / ".claude"
    dot_claude.mkdir(exist_ok=True)
    config_path = dot_claude / "praxion-rules.yaml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


# ===========================================================================
# Test 1: No project config → all 3 blacklistable rules injected
# ===========================================================================


def test_no_project_config_injects_all_blacklistable_rules(
    plugin_root: Path, project_dir: Path
) -> None:
    """When no .claude/praxion-rules.yaml exists, all 3 hook-deliver rules appear in output."""
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 with no project config. stderr: {result.stderr!r}"
    )
    context = _additional_context(result)
    assert context, (
        "Hook must emit additionalContext when no project config exists. Got empty output."
    )
    assert _FIXTURE_RULE_BODY.strip() in context, (
        "_fixture-rule body must appear in output when no blacklist is configured. "
        f"Context: {context!r}"
    )
    assert _AGENT_MODEL_ROUTING_BODY.strip() in context, (
        "agent-model-routing body must appear in output when no blacklist is configured. "
        f"Context: {context!r}"
    )
    assert _GIT_CONVENTIONS_BODY.strip() in context, (
        "vcs/git-conventions body must appear in output when no blacklist is configured. "
        f"Context: {context!r}"
    )


# ===========================================================================
# Test 2: disable: [swe/_fixture-rule] → 2 rules in output, _fixture-rule absent
# ===========================================================================


def test_disabling_one_rule_removes_it_from_injection(plugin_root: Path, project_dir: Path) -> None:
    """Disabling swe/_fixture-rule suppresses it; the other two rules are still injected."""
    _write_project_config(
        project_dir,
        "version: 1\ndisable:\n  - swe/_fixture-rule\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 when a valid blacklist exists. stderr: {result.stderr!r}"
    )
    context = _additional_context(result)
    assert _FIXTURE_RULE_BODY.strip() not in context, (
        "_fixture-rule body must NOT appear when disable: [swe/_fixture-rule] is set. "
        f"Context snippet: {context[:200]!r}"
    )
    assert _AGENT_MODEL_ROUTING_BODY.strip() in context, (
        "agent-model-routing body must still appear when only _fixture-rule is disabled. "
        f"Context snippet: {context[:200]!r}"
    )
    assert _GIT_CONVENTIONS_BODY.strip() in context, (
        "vcs/git-conventions body must still appear when only _fixture-rule is disabled. "
        f"Context snippet: {context[:200]!r}"
    )


# ===========================================================================
# Test 3: disable: [ml/*] → glob resolves cleanly; hook-deliver set unaffected
# ===========================================================================


def test_ml_glob_resolves_without_crash_and_hook_deliver_set_unaffected(
    plugin_root: Path, project_dir: Path
) -> None:
    """disable: [ml/*] resolves the glob without crashing.

    ML rules are path-scoped (install: symlink), so they are never in the
    hook-deliver set.  All 3 hook-deliver rules must still be injected.
    """
    _write_project_config(
        project_dir,
        "version: 1\ndisable:\n  - ml/*\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 when disable contains ml/* glob. stderr: {result.stderr!r}"
    )
    context = _additional_context(result)
    assert context, (
        "Hook must still emit additionalContext when ml/* is disabled "
        "(ML rules are not in hook-deliver set). Got empty output."
    )
    # All three hook-deliver rules must still be injected (ml/* doesn't match them).
    assert _FIXTURE_RULE_BODY.strip() in context, (
        f"_fixture-rule body must appear — it is not an ML rule. Context snippet: {context[:200]!r}"
    )
    assert _AGENT_MODEL_ROUTING_BODY.strip() in context, (
        "agent-model-routing body must appear — it is not an ML rule. "
        f"Context snippet: {context[:200]!r}"
    )
    assert _GIT_CONVENTIONS_BODY.strip() in context, (
        "vcs/git-conventions body must appear — it is not an ML rule. "
        f"Context snippet: {context[:200]!r}"
    )


# ===========================================================================
# Test 4: disable: [swe/agent-behavioral-contract] → warning on stderr, rule kept
# ===========================================================================


def test_disabling_core_rule_emits_warning_and_rule_stays_loaded(
    plugin_root: Path, project_dir: Path
) -> None:
    """Attempting to disable a core rule emits a stderr warning; the rule is not suppressed.

    The behavioral-contract rule has install: symlink (core), so it is never in
    the hook-deliver inject set regardless — but the warning must still fire.
    """
    _write_project_config(
        project_dir,
        "version: 1\ndisable:\n  - swe/agent-behavioral-contract\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 even when a core rule disable is attempted. stderr: {result.stderr!r}"
    )
    assert "swe/agent-behavioral-contract" in result.stderr, (
        "Hook must emit a warning naming the core rule that was attempted to disable. "
        f"stderr: {result.stderr!r}"
    )
    warning_keywords = ("warn", "core", "cannot", "non-disableable", "protect")
    stderr_lower = result.stderr.lower()
    has_warning_keyword = any(kw in stderr_lower for kw in warning_keywords)
    assert has_warning_keyword, (
        "stderr must contain a warning-indicating word (warn/core/cannot/non-disableable/protect). "
        f"stderr: {result.stderr!r}"
    )


# ===========================================================================
# Test 5: disable: [swe/*] → warnings for core rules; non-core swe/* suppressed
# ===========================================================================


def test_swe_glob_warns_for_core_rules_and_suppresses_non_core(
    plugin_root: Path, project_dir: Path
) -> None:
    """disable: [swe/*] catches core rules (warned, kept) and non-core swe/* rules (suppressed)."""
    _write_project_config(
        project_dir,
        "version: 1\ndisable:\n  - swe/*\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook must exit 0 with swe/* glob. stderr: {result.stderr!r}"
    # At least one core rule must be mentioned in stderr (warning fired).
    has_core_warning = any(core_id in result.stderr for core_id in _CORE_IDS)
    assert has_core_warning, (
        f"Hook must emit warnings for core rules swept by swe/* glob. stderr: {result.stderr!r}"
    )
    # swe/_fixture-rule and swe/agent-model-routing (non-core, hook-deliver, swe/*)
    # should be suppressed.
    context = _additional_context(result)
    assert _FIXTURE_RULE_BODY.strip() not in context, (
        "_fixture-rule (non-core, swe/*) must be suppressed by the swe/* glob. "
        f"Context snippet: {context[:200]!r}"
    )
    assert _AGENT_MODEL_ROUTING_BODY.strip() not in context, (
        "agent-model-routing (non-core, swe/*) must be suppressed by the swe/* glob. "
        f"Context snippet: {context[:200]!r}"
    )
    # swe/vcs/git-conventions: 'swe/*' does NOT match swe/vcs/git-conventions with fnmatch
    # at a single glob depth level — fnmatch('swe/vcs/git-conventions', 'swe/*') is False.
    # If the hook uses a one-level glob, git-conventions would survive.
    # If the hook uses recursive matching (** or path-prefix), it may be suppressed.
    # We do not assert on git-conventions here because the semantics depend on the
    # implementer's glob depth choice.  We assert only on the guaranteed behavior:
    # core rules warned + non-core direct swe/ rules suppressed.


# ===========================================================================
# Test 6: Malformed YAML project config → stderr log + fail open (all rules injected)
# ===========================================================================


def test_malformed_project_config_fails_open_with_all_rules_injected(
    plugin_root: Path, project_dir: Path
) -> None:
    """Malformed .claude/praxion-rules.yaml causes a stderr log and fail-open injection."""
    _write_project_config(
        project_dir,
        "version: 1\ndisable: [not closed\n  - swe/_fixture-rule\n:::bad: yaml:::\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 on malformed project config. stderr: {result.stderr!r}"
    )
    assert result.stderr, "Hook must log to stderr when project config is malformed."
    # Fail open: all 3 hook-deliver rules must be injected.
    context = _additional_context(result)
    assert _FIXTURE_RULE_BODY.strip() in context, (
        "_fixture-rule must be injected when project config is malformed (fail open). "
        f"Context snippet: {context[:200]!r}"
    )
    assert _AGENT_MODEL_ROUTING_BODY.strip() in context, (
        "agent-model-routing must be injected when project config is malformed (fail open). "
        f"Context snippet: {context[:200]!r}"
    )
    assert _GIT_CONVENTIONS_BODY.strip() in context, (
        "vcs/git-conventions must be injected when project config is malformed (fail open). "
        f"Context snippet: {context[:200]!r}"
    )


# ===========================================================================
# Test 7: version: 2 in project config → friendly stderr error + fail open
# ===========================================================================


def test_unsupported_schema_version_fails_open_with_friendly_error(
    plugin_root: Path, project_dir: Path
) -> None:
    """version: 2 in project config emits a friendly error on stderr and falls back to full injection."""
    _write_project_config(
        project_dir,
        "version: 2\ndisable:\n  - swe/_fixture-rule\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 on unsupported schema version. stderr: {result.stderr!r}"
    )
    # Must emit an error mentioning the unsupported version.
    stderr_lower = result.stderr.lower()
    has_version_error = any(
        kw in stderr_lower for kw in ("version", "schema", "not supported", "unsupported")
    )
    assert has_version_error, (
        f"stderr must mention the unsupported schema version. stderr: {result.stderr!r}"
    )
    # Fail open: all rules injected (disable list is ignored when schema is unknown).
    context = _additional_context(result)
    assert _FIXTURE_RULE_BODY.strip() in context, (
        "_fixture-rule must be injected on schema-version mismatch (fail open). "
        f"Context snippet: {context[:200]!r}"
    )
    assert _AGENT_MODEL_ROUTING_BODY.strip() in context, (
        "agent-model-routing must be injected on schema-version mismatch (fail open). "
        f"Context snippet: {context[:200]!r}"
    )
    assert _GIT_CONVENTIONS_BODY.strip() in context, (
        "vcs/git-conventions must be injected on schema-version mismatch (fail open). "
        f"Context snippet: {context[:200]!r}"
    )


# ===========================================================================
# Test 8: Missing manifest → stderr log + exit 0 (non-fatal)
# ===========================================================================


def test_missing_manifest_exits_zero_with_stderr_log(tmp_path: Path, project_dir: Path) -> None:
    """When CLAUDE_PLUGIN_ROOT has no rules/_manifest.yaml, hook logs to stderr and exits 0."""
    empty_plugin_root = tmp_path / "empty_plugin"
    empty_plugin_root.mkdir()
    # Do NOT call _make_manifest — the manifest is intentionally absent.
    result = _run_hook(empty_plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 when manifest is missing (non-fatal). stderr: {result.stderr!r}"
    )
    assert result.stderr, "Hook must log to stderr when manifest is missing."
    # No additionalContext output expected (nothing to inject without a manifest).
    # The key assertion is exit 0 (non-fatal) verified above.


# ===========================================================================
# Test 9: PRAXION_DISABLE_RULE_INJECTION=1 → exit 0, no additionalContext output
# ===========================================================================


def test_disable_env_var_suppresses_all_injection(plugin_root: Path, project_dir: Path) -> None:
    """PRAXION_DISABLE_RULE_INJECTION=1 causes the hook to exit 0 with no output."""
    result = _run_hook(
        plugin_root,
        project_dir,
        extra_env={"PRAXION_DISABLE_RULE_INJECTION": "1"},
    )
    assert result.returncode == 0, (
        f"Hook must exit 0 when PRAXION_DISABLE_RULE_INJECTION=1. stderr: {result.stderr!r}"
    )
    context = _additional_context(result)
    assert not context, (
        "Hook must emit no additionalContext when PRAXION_DISABLE_RULE_INJECTION=1. "
        f"Got: {context!r}"
    )
    # The hook must log to stderr that injection is disabled.
    assert result.stderr, "Hook must emit a stderr log line when PRAXION_DISABLE_RULE_INJECTION=1."


# ===========================================================================
# Test 10: Stderr summary line format matches expected pattern
# ===========================================================================


def test_stderr_summary_line_matches_expected_format(plugin_root: Path, project_dir: Path) -> None:
    """The hook emits a stderr summary line: [inject_rules] Loaded N core rules; injected M/T ..."""
    import re

    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"
    # Pattern: [inject_rules] Loaded <N> core rules; injected <M>/<T> hook-deliver rules (suppressed: ...); symlink suppressions via claudeMdExcludes: ...
    pattern = re.compile(
        r"\[inject_rules\]\s+Loaded\s+\d+\s+core\s+rules\s*;\s+"
        r"injected\s+\d+/\d+\s+hook-deliver\s+rules",
        re.IGNORECASE,
    )
    assert pattern.search(result.stderr), (
        "stderr must contain a summary line matching: "
        r"[inject_rules] Loaded N core rules; injected M/T hook-deliver rules ..."
        f"\nActual stderr: {result.stderr!r}"
    )


# ===========================================================================
# Test 11: Injection order matches manifest order (_fixture-rule → agent-model-routing → git-conventions)
# ===========================================================================


def test_injection_order_follows_manifest_order(plugin_root: Path, project_dir: Path) -> None:
    """Without blacklist, the 3 rules appear in manifest order in additionalContext."""
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"
    context = _additional_context(result)
    assert context, "Hook must emit additionalContext when no blacklist is configured."

    # Find positions of each rule's unique content marker.
    fixture_pos = context.find(_FIXTURE_RULE_BODY.strip()[:20])
    routing_pos = context.find(_AGENT_MODEL_ROUTING_BODY.strip()[:20])
    git_pos = context.find(_GIT_CONVENTIONS_BODY.strip()[:20])

    assert fixture_pos != -1, (
        f"_fixture-rule content not found in additionalContext. Context snippet: {context[:300]!r}"
    )
    assert routing_pos != -1, (
        "agent-model-routing content not found in additionalContext. "
        f"Context snippet: {context[:300]!r}"
    )
    assert git_pos != -1, (
        "vcs/git-conventions content not found in additionalContext. "
        f"Context snippet: {context[:300]!r}"
    )

    assert fixture_pos < routing_pos, (
        "_fixture-rule must appear before agent-model-routing in manifest order. "
        f"Positions: fixture={fixture_pos}, routing={routing_pos}"
    )
    assert routing_pos < git_pos, (
        "agent-model-routing must appear before vcs/git-conventions in manifest order. "
        f"Positions: routing={routing_pos}, git={git_pos}"
    )


# ===========================================================================
# Test 12: disable: [ml/*] → settings.json gets claudeMdExcludes for symlinked rules
# ===========================================================================


def test_disabling_symlink_rules_writes_claudemd_excludes(
    plugin_root: Path, project_dir: Path
) -> None:
    """Disabling install:symlink rules (ml/*) materializes claudeMdExcludes glob patterns in .claude/settings.json."""
    _write_project_config(project_dir, "version: 1\ndisable:\n  - ml/*\n")
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 when disabling symlinked rules. stderr: {result.stderr!r}"
    )

    settings_path = project_dir / ".claude" / "settings.json"
    assert settings_path.exists(), (
        "settings.json must be created when symlinked rules are disabled. "
        f"stderr: {result.stderr!r}"
    )

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    excludes = settings.get("claudeMdExcludes", [])
    expected = sorted(
        [
            "**/.claude/rules/ml/eval-driven-verification.md",
            "**/.claude/rules/ml/experiment-tracking-conventions.md",
            "**/.claude/rules/ml/gpu-budget-conventions.md",
        ]
    )
    assert sorted(excludes) == expected, (
        f"claudeMdExcludes must contain the three ml/* glob patterns. Got: {excludes!r}"
    )


# ===========================================================================
# Test 13: pre-existing user-managed claudeMdExcludes entries are preserved
# ===========================================================================


def test_user_managed_claudemd_excludes_preserved(plugin_root: Path, project_dir: Path) -> None:
    """Entries not starting with **/.claude/rules/ must survive reconciliation."""
    dot_claude = project_dir / ".claude"
    dot_claude.mkdir(exist_ok=True)
    settings_path = dot_claude / "settings.json"
    user_entries = [
        "**/monorepo/CLAUDE.md",
        "/home/user/other-team/.claude/rules/**",
    ]
    settings_path.write_text(
        json.dumps({"claudeMdExcludes": list(user_entries)}, indent=2),
        encoding="utf-8",
    )

    _write_project_config(project_dir, "version: 1\ndisable:\n  - ml/*\n")
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    excludes = settings.get("claudeMdExcludes", [])
    for entry in user_entries:
        assert entry in excludes, (
            f"User-managed entry {entry!r} must be preserved across reconciliation. "
            f"Got: {excludes!r}"
        )
    # Praxion-managed entries also present.
    assert "**/.claude/rules/ml/eval-driven-verification.md" in excludes, (
        f"Praxion-managed exclusion must be added. Got: {excludes!r}"
    )


# ===========================================================================
# Test 14: idempotent reconciliation — second run with same YAML does not rewrite
# ===========================================================================


def test_reconciliation_is_idempotent(plugin_root: Path, project_dir: Path) -> None:
    """A second SessionStart with unchanged YAML leaves settings.json mtime unchanged."""
    _write_project_config(project_dir, "version: 1\ndisable:\n  - ml/*\n")

    # First run: creates settings.json with claudeMdExcludes.
    first = _run_hook(plugin_root, project_dir)
    assert first.returncode == 0, f"First run failed. stderr: {first.stderr!r}"
    settings_path = project_dir / ".claude" / "settings.json"
    assert settings_path.exists(), "First run must create settings.json"
    mtime_before = settings_path.stat().st_mtime_ns

    # Second run with identical YAML: must not rewrite the file.
    second = _run_hook(plugin_root, project_dir)
    assert second.returncode == 0, f"Second run failed. stderr: {second.stderr!r}"
    mtime_after = settings_path.stat().st_mtime_ns

    assert mtime_before == mtime_after, (
        "settings.json must not be rewritten when reconciliation would produce "
        f"identical content. Before={mtime_before}, after={mtime_after}"
    )


# ===========================================================================
# Test 15: no praxion-rules.yaml → existing settings.json is left untouched
# ===========================================================================


def test_disabling_hook_deliver_rules_also_writes_claudemd_excludes(
    plugin_root: Path, project_dir: Path
) -> None:
    """Hook-deliver rules in the disable set also get claudeMdExcludes entries.

    Defense-in-depth: even though `install: hook-deliver` rules are primarily
    suppressed by filtering them out of `additionalContext`, the hook also
    emits `**/.claude/rules/<id>.md` exclusion globs for them. This neutralizes
    stale symlinks left by prior installs (when a rule's install type flipped
    from `symlink` to `hook-deliver`) — without this, Claude Code would keep
    loading the dangling links as user-scope memory files.
    """
    _write_project_config(
        project_dir,
        "version: 1\ndisable:\n"
        "  - swe/_fixture-rule\n"
        "  - swe/agent-model-routing\n"
        "  - swe/vcs/git-conventions\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 when disabling hook-deliver rules. stderr: {result.stderr!r}"
    )

    settings_path = project_dir / ".claude" / "settings.json"
    assert settings_path.exists(), (
        "settings.json must be created when hook-deliver rules are disabled, "
        "so a stale symlink for those rules cannot bypass the blacklist. "
        f"stderr: {result.stderr!r}"
    )

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    excludes = settings.get("claudeMdExcludes", [])
    expected = sorted(
        [
            "**/.claude/rules/swe/_fixture-rule.md",
            "**/.claude/rules/swe/agent-model-routing.md",
            "**/.claude/rules/swe/vcs/git-conventions.md",
        ]
    )
    assert sorted(excludes) == expected, (
        f"claudeMdExcludes must include exclusion globs for hook-deliver rules "
        f"(defense-in-depth against stale symlinks). Got: {excludes!r}"
    )


# ===========================================================================
# Test 16: disable: as a YAML scalar emits a warning instead of silent no-op
# ===========================================================================


def test_disable_as_scalar_emits_warning_and_treats_as_empty(
    plugin_root: Path, project_dir: Path
) -> None:
    """`disable: ml/*` (scalar) is a common typo for `disable: [ml/*]`.

    The hook must surface this with a stderr warning rather than silently
    treating the field as empty. Fail-open behavior is preserved: all
    hook-deliver rules still inject.
    """
    _write_project_config(project_dir, "version: 1\ndisable: ml/*\n")
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 even with malformed disable: scalar. stderr: {result.stderr!r}"
    )
    stderr_lower = result.stderr.lower()
    assert "disable" in stderr_lower, (
        f"stderr must warn that 'disable:' should be a list. stderr: {result.stderr!r}"
    )
    assert "list" in stderr_lower, (
        f"stderr must warn that 'disable:' should be a list. stderr: {result.stderr!r}"
    )
    # Fail-open: all 3 rules still injected.
    context = _additional_context(result)
    assert _FIXTURE_RULE_BODY.strip() in context, (
        f"Scalar disable: must fail-open with all rules injected. Context: {context[:200]!r}"
    )


# ===========================================================================
# Test 17: a disable: pattern matching zero rule IDs emits a typo warning
# ===========================================================================


def test_unmatched_disable_pattern_emits_typo_warning(plugin_root: Path, project_dir: Path) -> None:
    """A disable: entry that matches no manifest rule is almost always a typo."""
    _write_project_config(
        project_dir,
        "version: 1\ndisable:\n  - swe/no-such-rule\n  - typo/at-all\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 with unmatched patterns. stderr: {result.stderr!r}"
    )
    # Each unmatched pattern must produce a stderr warning naming it.
    assert "swe/no-such-rule" in result.stderr, (
        f"stderr must mention the unmatched pattern. stderr: {result.stderr!r}"
    )
    assert "typo/at-all" in result.stderr, (
        f"stderr must mention each unmatched pattern. stderr: {result.stderr!r}"
    )


# ===========================================================================
# Test 18: non-integer version: value emits a warning and coerces to 1
# ===========================================================================


def test_non_int_version_emits_warning_and_coerces(plugin_root: Path, project_dir: Path) -> None:
    """`version: "1"` (string) is silently coerced to int 1 — but the hook
    surfaces the wrong shape with a stderr warning so the user sees it."""
    _write_project_config(project_dir, 'version: "1"\ndisable: []\n')
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"
    stderr_lower = result.stderr.lower()
    assert "version" in stderr_lower, (
        f"stderr must mention the version field. stderr: {result.stderr!r}"
    )
    # Coerced to 1, so disable list still processed → no unsupported-version warning
    assert "not supported" not in stderr_lower, (
        f"Coercion to 1 must not trigger the unsupported-version path. stderr: {result.stderr!r}"
    )


# ===========================================================================
# Test 19: malformed settings.json prints a loud, actionable warning
# ===========================================================================


def test_malformed_settings_json_emits_loud_warning(plugin_root: Path, project_dir: Path) -> None:
    """When .claude/settings.json is invalid JSON, the disable list is silently
    dropped (Claude Code can't read excludes). The hook must surface this
    failure with a warning that names the consequence."""
    dot_claude = project_dir / ".claude"
    dot_claude.mkdir()
    (dot_claude / "settings.json").write_text("{ this is not valid json", encoding="utf-8")

    _write_project_config(project_dir, "version: 1\ndisable:\n  - ml/*\n")
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"
    # The warning must mention BOTH that parsing failed AND that the disable
    # list will not be applied — earlier versions only said the former, which
    # silently degraded the contract.
    assert "could not parse" in result.stderr.lower(), (
        f"stderr must report the JSON parse failure. stderr: {result.stderr!r}"
    )
    assert "not be applied" in result.stderr.lower() or "skipped" in result.stderr.lower(), (
        f"stderr must surface the consequence (disable list not applied). stderr: {result.stderr!r}"
    )


# ===========================================================================
# Test 20: top-level settings.json key ordering is preserved across runs
# ===========================================================================


def test_existing_settings_json_key_ordering_preserved(
    plugin_root: Path, project_dir: Path
) -> None:
    """The hook must not alphabetize user-managed top-level keys in
    .claude/settings.json. claudeMdExcludes itself is sorted (deterministic
    output) but unrelated keys keep their original position."""
    dot_claude = project_dir / ".claude"
    dot_claude.mkdir()
    settings_path = dot_claude / "settings.json"
    # Keys deliberately not in alphabetical order:
    settings_path.write_text(
        json.dumps(
            {"zzz_user_key": "first", "aaa_user_key": "second"},
            indent=2,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _write_project_config(project_dir, "version: 1\ndisable:\n  - ml/*\n")

    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"

    final = settings_path.read_text(encoding="utf-8")
    # zzz must appear BEFORE aaa in the file body because that was the
    # original insertion order. sort_keys=True would have swapped them.
    zzz_pos = final.index("zzz_user_key")
    aaa_pos = final.index("aaa_user_key")
    assert zzz_pos < aaa_pos, (
        "User-managed top-level keys must retain insertion order across"
        f" reconciliation. File:\n{final}"
    )


def test_no_yaml_leaves_existing_settings_untouched(plugin_root: Path, project_dir: Path) -> None:
    """Without praxion-rules.yaml, the hook must not create or modify settings.json."""
    dot_claude = project_dir / ".claude"
    dot_claude.mkdir()
    settings_path = dot_claude / "settings.json"
    initial_content = (
        json.dumps(
            {
                "claudeMdExcludes": ["**/monorepo/CLAUDE.md"],
                "someOtherSetting": True,
            },
            indent=2,
        )
        + "\n"
    )
    settings_path.write_text(initial_content, encoding="utf-8")
    mtime_before = settings_path.stat().st_mtime_ns

    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"

    mtime_after = settings_path.stat().st_mtime_ns
    assert mtime_before == mtime_after, (
        "settings.json must not be modified when no praxion-rules.yaml exists. "
        f"Before={mtime_before}, after={mtime_after}"
    )
    final_content = settings_path.read_text(encoding="utf-8")
    assert final_content == initial_content, (
        "settings.json content must be byte-identical when no YAML config exists. "
        f"Before: {initial_content!r}\nAfter: {final_content!r}"
    )


# ===========================================================================
# A skipped injection is surfaced to the session, never stderr-only
# ===========================================================================


def test_missing_pyyaml_tells_the_session_rules_were_not_loaded(
    plugin_root: Path, project_dir: Path
) -> None:
    """The first python3 on PATH often lacks PyYAML (PEP 668 system pythons,
    fresh Homebrew). The skip must reach the session naming the interpreter
    and the fix — stderr alone is invisible to both the model and the user."""
    blocked_yaml = (
        "import runpy, sys; sys.modules['yaml'] = None; "
        f"sys.path.insert(0, {str(HOOK_SCRIPT.parent)!r}); "
        f"runpy.run_path({str(HOOK_SCRIPT)!r}, run_name='__main__')"
    )
    result = subprocess.run(
        [sys.executable, "-c", blocked_yaml],
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=_hook_env(plugin_root),
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    context = _additional_context(result)
    assert "were NOT loaded" in context
    assert sys.executable in context


def test_missing_manifest_tells_the_session_rules_were_not_loaded(
    tmp_path: Path, project_dir: Path
) -> None:
    empty_plugin_root = tmp_path / "empty_plugin"
    empty_plugin_root.mkdir()

    result = _run_hook(empty_plugin_root, project_dir)

    assert result.returncode == 0, result.stderr
    context = _additional_context(result)
    assert "were NOT loaded" in context
    assert "manifest not found" in context


def _import_hook_module():
    # A plain import, not a path load: the mutation sensor only counts calls that reach the
    # module it relocates through the import system.
    import inject_rules

    return inject_rules


def test_pyyaml_fix_never_suggests_pip_for_an_externally_managed_interpreter() -> None:
    """PEP 668 interpreters (Homebrew, Debian system python) refuse `pip
    install`; advising it would dead-end the user on the machines that hit
    this most."""
    module = _import_hook_module()

    fix = module._pyyaml_fix("/opt/homebrew/bin/python3", externally_managed=True)

    assert "pip install" not in fix
    assert "first on PATH" in fix


def test_pyyaml_fix_suggests_pip_for_a_pip_managed_interpreter() -> None:
    module = _import_hook_module()

    fix = module._pyyaml_fix("/usr/local/bin/python3", externally_managed=False)

    assert "`/usr/local/bin/python3 -m pip install pyyaml`" in fix


# ===========================================================================
# Residents: disabling a rule suppresses the one-line projection that stands for it
# ===========================================================================

_RESIDENT_BODY = "## Model Routing Resident\n\nOne line of the model routing rule.\n"
_RESIDENT_ID = "residents/model-routing"  # outside swe/ so a swe/* glob never names it directly


def _add_resident(plugin_root: Path, parent_path: str, *, core: bool = False) -> None:
    """Add a hook-deliver resident of `parent_path` to the synthetic plugin root."""
    resident = plugin_root / "rules" / "residents" / "model-routing.md"
    resident.parent.mkdir(parents=True, exist_ok=True)
    resident.write_text(f"---\nresident_of: {parent_path}\n---\n{_RESIDENT_BODY}", encoding="utf-8")
    manifest = plugin_root / "rules" / "_manifest.yaml"
    row = (
        f"- id: {_RESIDENT_ID}\n"
        "  path: rules/residents/model-routing.md\n"
        "  load: always_on\n"
        f"  core: {str(core).lower()}\n"
        "  install: hook-deliver\n"
        "  chars: 100\n"
    )
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("categories:", row + "categories:", 1),
        encoding="utf-8",
    )


def _disable(project_dir: Path, *patterns: str) -> None:
    items = "".join(f"  - {pattern}\n" for pattern in patterns)
    _write_project_config(project_dir, f"version: 1\ndisable:\n{items}")


def test_disabling_a_rule_by_id_suppresses_its_resident(
    plugin_root: Path, project_dir: Path
) -> None:
    _add_resident(plugin_root, "rules/swe/agent-model-routing.md")
    _disable(project_dir, "swe/agent-model-routing")

    result = _run_hook(plugin_root, project_dir)

    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    context = _additional_context(result)
    assert _RESIDENT_BODY.strip() not in context, "the resident must go with its disabled parent"
    assert _GIT_CONVENTIONS_BODY.strip() in context, "an unrelated rule must stay injected"
    excludes = json.loads((project_dir / ".claude" / "settings.json").read_text())[
        "claudeMdExcludes"
    ]
    assert f"**/.claude/rules/{_RESIDENT_ID}.md" in excludes


def test_disabling_a_rule_by_glob_suppresses_its_resident(
    plugin_root: Path, project_dir: Path
) -> None:
    _add_resident(plugin_root, "rules/swe/agent-model-routing.md")
    _disable(project_dir, "swe/*")

    result = _run_hook(plugin_root, project_dir)

    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    assert _RESIDENT_BODY.strip() not in _additional_context(result)


def test_a_resident_whose_parent_is_not_disabled_is_still_injected(
    plugin_root: Path, project_dir: Path
) -> None:
    _add_resident(plugin_root, "rules/swe/agent-model-routing.md")
    _disable(project_dir, "swe/_fixture-rule")

    result = _run_hook(plugin_root, project_dir)

    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    context = _additional_context(result)
    assert _RESIDENT_BODY.strip() in context
    assert _AGENT_MODEL_ROUTING_BODY.strip() in context


def test_a_resident_of_a_core_parent_stays_when_the_parent_cannot_be_disabled(
    plugin_root: Path, project_dir: Path
) -> None:
    _add_resident(plugin_root, "rules/swe/agent-behavioral-contract.md")
    _disable(project_dir, "swe/agent-behavioral-contract")

    result = _run_hook(plugin_root, project_dir)

    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    assert "cannot disable core rule" in result.stderr
    assert _RESIDENT_BODY.strip() in _additional_context(result)


def test_a_core_resident_stays_even_when_its_parent_is_disabled(
    plugin_root: Path, project_dir: Path
) -> None:
    _add_resident(plugin_root, "rules/swe/agent-model-routing.md", core=True)
    _disable(project_dir, "swe/agent-model-routing")

    result = _run_hook(plugin_root, project_dir)

    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    assert _RESIDENT_BODY.strip() in _additional_context(result)


def test_a_resident_listed_in_the_manifest_but_unreadable_stays_injected_and_exits_zero(
    plugin_root: Path, project_dir: Path
) -> None:
    _add_resident(plugin_root, "rules/swe/agent-model-routing.md")
    (plugin_root / "rules" / "residents" / "model-routing.md").unlink()
    _disable(project_dir, "swe/agent-model-routing")

    result = _run_hook(plugin_root, project_dir)

    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    assert "could not read rule file" in result.stderr


def test_the_summary_line_names_the_parent_and_its_resident_as_suppressed(
    plugin_root: Path, project_dir: Path
) -> None:
    _add_resident(plugin_root, "rules/swe/agent-model-routing.md")
    _disable(project_dir, "swe/agent-model-routing")

    result = _run_hook(plugin_root, project_dir)

    summary = next(line for line in result.stderr.splitlines() if "(suppressed:" in line)
    suppressed, _, excludes = summary.partition("claudeMdExcludes entries:")
    assert "swe/agent-model-routing" in suppressed
    assert _RESIDENT_ID in suppressed
    assert "swe/agent-model-routing" in excludes
    assert _RESIDENT_ID in excludes


# Same cases as tests/test_export_cursor_rules_resident.py: the two local checks and the shared
# reader must agree on a malformed frontmatter as well as on a well-formed one.
_RESIDENT_TEXTS = {
    "resident": "---\nresident_of: rules/swe/rule.md\n---\n## Rule\n\nOne line of it.\n",
    "rule": "---\npaths:\n  - 'docs/**'\n---\n## Rule\n\nThe whole rule.\n",
    "quoted": "---\n'resident_of': \"rules/swe/rule.md\"\n---\nBody.\n",
    "empty": "---\nresident_of:\n---\nBody.\n",
    "indented": "---\n  resident_of: rules/swe/rule.md\n---\nBody.\n",
    "unclosed": "---\nresident_of: rules/swe/rule.md\nBody, never closed.\n",
    "none": "No frontmatter; resident_of: rules/swe/rule.md\n",
    "in-body": "---\npaths: ['docs/**']\n---\nresident_of: rules/swe/rule.md\n",
    "non-md-value": "---\nresident_of: not-a-rule-path\n---\nBody.\n",
    "empty-frontmatter": "---\n---\nresident_of: rules/swe/rule.md\n",
    "padded-delimiters": "---  \nresident_of: rules/swe/rule.md\n---  \nBody.\n",
    "single-quoted-value": "---\nresident_of: 'rules/swe/rule.md'\n---\nBody.\n",
    "later-key": "---\npaths: ['a']\nresident_of: rules/swe/rule.md\n---\nBody.\n",
    "longer-key": "---\nresident_ofx: rules/swe/rule.md\n---\nBody.\n",
}


def _shared_resident_reader():
    """Load scripts/_resident_of.py from the nearest ancestor that carries it.

    Walking up, not importing `scripts`, keeps the test working when a mutation
    run relocates it under `hooks/mutants/`, where the repository root is not on
    the import path.
    """
    import importlib.util

    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "scripts" / "_resident_of.py"
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("resident_of_shared", candidate)
            assert spec is not None
            assert spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise AssertionError("scripts/_resident_of.py not found above this test")


@pytest.mark.parametrize("text", _RESIDENT_TEXTS.values(), ids=_RESIDENT_TEXTS.keys())
def test_the_injectors_resident_check_agrees_with_the_shared_reader(text: str) -> None:
    shared = _shared_resident_reader().resident_parent

    assert _import_hook_module()._resident_parent(text) == shared(text)


def _rule_row(
    rule_id: str, path: str, *, install: str = "hook-deliver", core: bool = False
) -> dict:
    return {"id": rule_id, "path": path, "install": install, "core": core}


def _write_rule(plugin_root: Path, rel_path: str, frontmatter: str) -> None:
    path = plugin_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\nBody.\n", encoding="utf-8")


def test_a_disabled_rule_adds_only_the_hook_deliver_non_core_residents_that_name_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _import_hook_module()
    _write_rule(tmp_path, "rules/a/resident.md", "resident_of: rules/swe/parent.md")
    _write_rule(tmp_path, "rules/a/other.md", "resident_of: rules/swe/other-parent.md")
    _write_rule(tmp_path, "rules/a/core.md", "resident_of: rules/swe/parent.md")
    _write_rule(tmp_path, "rules/a/linked.md", "resident_of: rules/swe/parent.md")
    _write_rule(tmp_path, "rules/a/plain.md", "paths: ['docs/**']")
    rules = [
        _rule_row("a/resident", "rules/a/resident.md"),
        _rule_row("a/other", "rules/a/other.md"),
        _rule_row("a/core", "rules/a/core.md", core=True),
        _rule_row("a/linked", "rules/a/linked.md", install="symlink"),
        _rule_row("a/plain", "rules/a/plain.md"),
        {"id": "a/pathless", "install": "hook-deliver"},
    ]

    disabled = module._add_residents_of_disabled({"swe/parent"}, rules, tmp_path)

    assert disabled == {"swe/parent", "a/resident"}
    assert capsys.readouterr().err == "", "a row without a path is no resident, not a read failure"


def test_an_empty_disable_set_reads_no_rule_file(tmp_path: Path) -> None:
    module = _import_hook_module()
    rules = [_rule_row("a/resident", "rules/a/missing.md")]

    assert module._add_residents_of_disabled(set(), rules, tmp_path) == set()


def test_an_unreadable_resident_file_is_kept_and_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _import_hook_module()
    rules = [_rule_row("a/resident", "rules/a/missing.md")]

    disabled = module._add_residents_of_disabled({"swe/parent"}, rules, tmp_path)

    assert disabled == {"swe/parent"}
    warning = capsys.readouterr().err
    assert "[inject_rules] WARNING: could not read rule file" in warning
    assert str(tmp_path / "rules" / "a" / "missing.md") in warning
