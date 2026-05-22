"""Tests for hooks/inject_rules.py — SessionStart rule-injection hook.

Verifies the eleven behavioral contracts:

  1. No project config → all 3 blacklistable rules in additionalContext output
  2. disable: [swe/memory-protocol] → 2 rules in output, memory-protocol absent
  3. disable: [ml/*] → glob resolves without crash; hook-deliver set unaffected
  4. disable: [swe/agent-behavioral-contract] → stderr warning; rule kept (core protection)
  5. disable: [swe/*] → warnings for core rules; non-core swe/* rules suppressed
  6. Malformed YAML project config → stderr log + fail open (all rules injected)
  7. version: 2 in project config → friendly stderr error + fail open (all rules injected)
  8. Missing manifest → stderr log + exit 0 (non-fatal)
  9. PRAXION_DISABLE_RULE_INJECTION=1 → exit 0, no additionalContext output
  10. Stderr summary line format validated
  11. Injection order: rules appear in manifest order (memory-protocol → agent-model-routing
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

_MEMORY_PROTOCOL_BODY = "## Memory Protocol\n\nThis is the memory protocol rule body.\n"
_AGENT_MODEL_ROUTING_BODY = (
    "## Agent Model Routing\n\nThis is the model routing rule body.\n"
)
_GIT_CONVENTIONS_BODY = "## Git Conventions\n\nThis is the git conventions rule body.\n"

# Core rule IDs the hook must refuse to suppress.
_CORE_IDS = [
    "swe/agent-behavioral-contract",
    "swe/swe-agent-coordination-protocol",
    "swe/agent-intermediate-documents",
    "swe/adr-conventions",
    "CLAUDE",
]

# Hook-deliver rule IDs (the three blacklistable always-loaded rules).
_HOOK_DELIVER_IDS = [
    "swe/memory-protocol",
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
    (rules_dir / "swe" / "memory-protocol.md").write_text(
        _MEMORY_PROTOCOL_BODY, encoding="utf-8"
    )
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
        "CLAUDE": "rules/CLAUDE.md",
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
        ("swe/memory-protocol", "rules/swe/memory-protocol.md"),
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

    (rules_dir / "_manifest.yaml").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8"
    )


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
    env = {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
    }
    # Neutralize the ambient memory-MCP opt-out (set in this repo's
    # .claude/settings.json) so tests are deterministic regardless of the
    # session env. Tests that exercise it pass it explicitly via extra_env.
    env.pop("PRAXION_DISABLE_MEMORY_MCP", None)
    env.update(extra_env or {})
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


@pytest.fixture()
def plugin_root(tmp_path: Path) -> Path:
    """A synthetic CLAUDE_PLUGIN_ROOT with a populated rules/_manifest.yaml."""
    _make_manifest(tmp_path)
    return tmp_path


@pytest.fixture()
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
        "Hook must emit additionalContext when no project config exists. "
        "Got empty output."
    )
    assert _MEMORY_PROTOCOL_BODY.strip() in context, (
        "memory-protocol body must appear in output when no blacklist is configured. "
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
# Test 2: disable: [swe/memory-protocol] → 2 rules in output, memory-protocol absent
# ===========================================================================


def test_disabling_one_rule_removes_it_from_injection(
    plugin_root: Path, project_dir: Path
) -> None:
    """Disabling swe/memory-protocol suppresses it; the other two rules are still injected."""
    _write_project_config(
        project_dir,
        "version: 1\ndisable:\n  - swe/memory-protocol\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 when a valid blacklist exists. stderr: {result.stderr!r}"
    )
    context = _additional_context(result)
    assert _MEMORY_PROTOCOL_BODY.strip() not in context, (
        "memory-protocol body must NOT appear when disable: [swe/memory-protocol] is set. "
        f"Context snippet: {context[:200]!r}"
    )
    assert _AGENT_MODEL_ROUTING_BODY.strip() in context, (
        "agent-model-routing body must still appear when only memory-protocol is disabled. "
        f"Context snippet: {context[:200]!r}"
    )
    assert _GIT_CONVENTIONS_BODY.strip() in context, (
        "vcs/git-conventions body must still appear when only memory-protocol is disabled. "
        f"Context snippet: {context[:200]!r}"
    )


# ===========================================================================
# Test 2b: PRAXION_DISABLE_MEMORY_MCP=1 (no blacklist) → memory-protocol absent
# ===========================================================================


def test_memory_mcp_disabled_env_suppresses_memory_protocol(
    plugin_root: Path, project_dir: Path
) -> None:
    """PRAXION_DISABLE_MEMORY_MCP=1 structurally suppresses memory-protocol even
    with no project blacklist; the other two hook-deliver rules still inject."""
    result = _run_hook(
        plugin_root,
        project_dir,
        extra_env={"PRAXION_DISABLE_MEMORY_MCP": "1"},
    )
    assert result.returncode == 0, (
        f"Hook must exit 0 when memory MCP is disabled via env. stderr: {result.stderr!r}"
    )
    context = _additional_context(result)
    assert _MEMORY_PROTOCOL_BODY.strip() not in context, (
        "memory-protocol body must NOT appear when PRAXION_DISABLE_MEMORY_MCP=1. "
        f"Context snippet: {context[:200]!r}"
    )
    assert _AGENT_MODEL_ROUTING_BODY.strip() in context, (
        "agent-model-routing must still appear when only memory MCP is disabled. "
        f"Context snippet: {context[:200]!r}"
    )
    assert _GIT_CONVENTIONS_BODY.strip() in context, (
        "vcs/git-conventions must still appear when only memory MCP is disabled. "
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
    assert _MEMORY_PROTOCOL_BODY.strip() in context, (
        "memory-protocol body must appear — it is not an ML rule. "
        f"Context snippet: {context[:200]!r}"
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
    assert result.returncode == 0, (
        f"Hook must exit 0 with swe/* glob. stderr: {result.stderr!r}"
    )
    # At least one core rule must be mentioned in stderr (warning fired).
    has_core_warning = any(core_id in result.stderr for core_id in _CORE_IDS)
    assert has_core_warning, (
        "Hook must emit warnings for core rules swept by swe/* glob. "
        f"stderr: {result.stderr!r}"
    )
    # swe/memory-protocol and swe/agent-model-routing (non-core, hook-deliver, swe/*)
    # should be suppressed.
    context = _additional_context(result)
    assert _MEMORY_PROTOCOL_BODY.strip() not in context, (
        "memory-protocol (non-core, swe/*) must be suppressed by the swe/* glob. "
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
        "version: 1\ndisable: [not closed\n  - swe/memory-protocol\n:::bad: yaml:::\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 on malformed project config. stderr: {result.stderr!r}"
    )
    assert result.stderr, "Hook must log to stderr when project config is malformed."
    # Fail open: all 3 hook-deliver rules must be injected.
    context = _additional_context(result)
    assert _MEMORY_PROTOCOL_BODY.strip() in context, (
        "memory-protocol must be injected when project config is malformed (fail open). "
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
        "version: 2\ndisable:\n  - swe/memory-protocol\n",
    )
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, (
        f"Hook must exit 0 on unsupported schema version. stderr: {result.stderr!r}"
    )
    # Must emit an error mentioning the unsupported version.
    stderr_lower = result.stderr.lower()
    has_version_error = any(
        kw in stderr_lower
        for kw in ("version", "schema", "not supported", "unsupported")
    )
    assert has_version_error, (
        f"stderr must mention the unsupported schema version. stderr: {result.stderr!r}"
    )
    # Fail open: all rules injected (disable list is ignored when schema is unknown).
    context = _additional_context(result)
    assert _MEMORY_PROTOCOL_BODY.strip() in context, (
        "memory-protocol must be injected on schema-version mismatch (fail open). "
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


def test_missing_manifest_exits_zero_with_stderr_log(
    tmp_path: Path, project_dir: Path
) -> None:
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


def test_disable_env_var_suppresses_all_injection(
    plugin_root: Path, project_dir: Path
) -> None:
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
    assert result.stderr, (
        "Hook must emit a stderr log line when PRAXION_DISABLE_RULE_INJECTION=1."
    )


# ===========================================================================
# Test 10: Stderr summary line format matches expected pattern
# ===========================================================================


def test_stderr_summary_line_matches_expected_format(
    plugin_root: Path, project_dir: Path
) -> None:
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
# Test 11: Injection order matches manifest order (memory-protocol → agent-model-routing → git-conventions)
# ===========================================================================


def test_injection_order_follows_manifest_order(
    plugin_root: Path, project_dir: Path
) -> None:
    """Without blacklist, the 3 rules appear in manifest order in additionalContext."""
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"
    context = _additional_context(result)
    assert context, "Hook must emit additionalContext when no blacklist is configured."

    # Find positions of each rule's unique content marker.
    memory_pos = context.find(_MEMORY_PROTOCOL_BODY.strip()[:20])
    routing_pos = context.find(_AGENT_MODEL_ROUTING_BODY.strip()[:20])
    git_pos = context.find(_GIT_CONVENTIONS_BODY.strip()[:20])

    assert memory_pos != -1, (
        "memory-protocol content not found in additionalContext. "
        f"Context snippet: {context[:300]!r}"
    )
    assert routing_pos != -1, (
        "agent-model-routing content not found in additionalContext. "
        f"Context snippet: {context[:300]!r}"
    )
    assert git_pos != -1, (
        "vcs/git-conventions content not found in additionalContext. "
        f"Context snippet: {context[:300]!r}"
    )

    assert memory_pos < routing_pos, (
        "memory-protocol must appear before agent-model-routing in manifest order. "
        f"Positions: memory={memory_pos}, routing={routing_pos}"
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


def test_user_managed_claudemd_excludes_preserved(
    plugin_root: Path, project_dir: Path
) -> None:
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
        "  - swe/memory-protocol\n"
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
            "**/.claude/rules/swe/memory-protocol.md",
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
    assert "disable" in stderr_lower and "list" in stderr_lower, (
        f"stderr must warn that 'disable:' should be a list. stderr: {result.stderr!r}"
    )
    # Fail-open: all 3 rules still injected.
    context = _additional_context(result)
    assert _MEMORY_PROTOCOL_BODY.strip() in context, (
        "Scalar disable: must fail-open with all rules injected."
        f" Context: {context[:200]!r}"
    )


# ===========================================================================
# Test 17: a disable: pattern matching zero rule IDs emits a typo warning
# ===========================================================================


def test_unmatched_disable_pattern_emits_typo_warning(
    plugin_root: Path, project_dir: Path
) -> None:
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


def test_non_int_version_emits_warning_and_coerces(
    plugin_root: Path, project_dir: Path
) -> None:
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
        f"Coercion to 1 must not trigger the unsupported-version path."
        f" stderr: {result.stderr!r}"
    )


# ===========================================================================
# Test 19: malformed settings.json prints a loud, actionable warning
# ===========================================================================


def test_malformed_settings_json_emits_loud_warning(
    plugin_root: Path, project_dir: Path
) -> None:
    """When .claude/settings.json is invalid JSON, the disable list is silently
    dropped (Claude Code can't read excludes). The hook must surface this
    failure with a warning that names the consequence."""
    dot_claude = project_dir / ".claude"
    dot_claude.mkdir()
    (dot_claude / "settings.json").write_text(
        "{ this is not valid json", encoding="utf-8"
    )

    _write_project_config(project_dir, "version: 1\ndisable:\n  - ml/*\n")
    result = _run_hook(plugin_root, project_dir)
    assert result.returncode == 0, f"Hook failed. stderr: {result.stderr!r}"
    # The warning must mention BOTH that parsing failed AND that the disable
    # list will not be applied — earlier versions only said the former, which
    # silently degraded the contract.
    assert "could not parse" in result.stderr.lower(), (
        f"stderr must report the JSON parse failure. stderr: {result.stderr!r}"
    )
    assert (
        "not be applied" in result.stderr.lower() or "skipped" in result.stderr.lower()
    ), (
        "stderr must surface the consequence (disable list not applied)."
        f" stderr: {result.stderr!r}"
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


def test_no_yaml_leaves_existing_settings_untouched(
    plugin_root: Path, project_dir: Path
) -> None:
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
