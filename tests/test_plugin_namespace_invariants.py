"""Invariants for the plugin's namespace identity.

The plugin was renamed from its original identifier to ``praxion``. Every
namespaced surface moved with it: agents and skills resolve as
``praxion:<name>``, commands as ``/praxion:<name>``, and MCP tools as
``mcp__plugin_praxion_<server>__<tool>``.

Two distinct things are asserted here, and the second is the one that matters:

1. The manifest declares the current name.
2. **No live surface still carries the retired one**, and the runtime
   predicates actively *reject* it. A rename of this shape fails **silently** --
   a missed ``startswith`` leaves an agent simply not recognised as
   Praxion-native, with no error and no failing assertion anywhere. So the
   canaries below drive the retired value and assert rejection, rather than
   driving the current value and asserting acceptance, which would pass either
   way (`rules/swe/gate-liveness.md`, "a gate must be proven to bite").

Historical records under ``.ai-state/`` are deliberately exempt. An ADR or an
archived report naming the old identifier remains true as a record of what was
so when it was written; rewriting history to match the present is what the
frozen-artifact conventions forbid.

The retired token is assembled at runtime rather than written literally, so
this module does not match its own repository scan.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

CURRENT_NAMESPACE = "praxion"
# Assembled, never spelled: a literal here would be found by the scan below.
RETIRED_NAMESPACE = "i" + "-am"

# Live files permitted to name the retired namespace, each with its reason.
# Deliberately a per-file allowlist rather than a pattern: migration guidance has
# to spell the old token so a reader can grep their own project for it, whereas
# any *new* file naming it is precisely what this gate exists to catch. Entries
# are validated below, so a stale one fails rather than silently widening scope.
MIGRATION_REFERENCES: dict[str, str] = {
    "commands/upgrade-project.md": (
        "documents the manual step for projects onboarded before the rename (td-145)"
    ),
}

# Records of what was true when written. See the module docstring.
HISTORICAL_PATHS: tuple[str, ...] = (
    ".ai-state/decisions/",
    ".ai-state/observations.jsonl",
    ".ai-state/TECH_DEBT_RESOLVED.md",
    ".ai-state/sentinel_reports/",
    ".ai-state/skill_genesis_reports/",
    ".ai-state/praxion_eval_reports/",
    ".ai-state/specs/",
    ".ai-state/calibration_log.md",
)


def _load_hook(name: str):
    """Import a hook by path.

    Hooks are standalone scripts rather than a package, and they import each
    other by bare name (``from _hook_utils import ...``), so ``hooks/`` has to
    be on ``sys.path`` before the module body executes.
    """
    hooks_dir = str(REPO_ROOT / "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "hooks" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _is_historical(path: str) -> bool:
    return path.startswith(HISTORICAL_PATHS)


def test_manifest_declares_the_current_namespace():
    manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == CURRENT_NAMESPACE


def test_no_live_surface_carries_the_retired_namespace():
    offenders: list[str] = []
    for rel in _tracked_files():
        if _is_historical(rel) or rel in MIGRATION_REFERENCES:
            continue
        path = REPO_ROOT / rel
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable; nothing to assert
        if RETIRED_NAMESPACE in content:
            offenders.append(rel)

    assert not offenders, (
        f"{len(offenders)} live file(s) still carry the retired plugin namespace "
        f"and would silently stop resolving: {sorted(offenders)}"
    )


def test_historical_records_are_left_intact():
    """The exemption must be a real carve-out, not a vacuous one.

    If this ever finds nothing, the scan above is passing for the wrong reason --
    history was rewritten, or the exempt paths no longer exist.
    """
    preserved = [
        rel
        for rel in _tracked_files()
        if _is_historical(rel) and RETIRED_NAMESPACE in (REPO_ROOT / rel).read_text(errors="ignore")
    ]
    assert preserved, (
        "no historical record carries the retired namespace -- either history was "
        "rewritten to match the present, or HISTORICAL_PATHS no longer resolves"
    )


@pytest.mark.parametrize(("path", "reason"), sorted(MIGRATION_REFERENCES.items()))
def test_each_migration_reference_is_still_earning_its_exemption(path, reason):
    """An allowlist entry that no longer applies quietly widens the gate's blind spot."""
    target = REPO_ROOT / path
    assert target.exists(), f"{path} is allowlisted but does not exist ({reason})"
    assert RETIRED_NAMESPACE in target.read_text(encoding="utf-8"), (
        f"{path} no longer names the retired namespace -- drop it from "
        f"MIGRATION_REFERENCES rather than leaving a dead exemption ({reason})"
    )


@pytest.mark.parametrize("agent_type", ["researcher", "implementer", "sentinel"])
def test_retired_prefix_is_not_recognised_as_praxion_native(agent_type):
    """Canary: reverting the predicate to the retired prefix must fail here."""
    module = _load_hook("inject_subagent_context")
    assert module._is_praxion_native(f"{CURRENT_NAMESPACE}:{agent_type}") is True
    assert module._is_praxion_native(f"{RETIRED_NAMESPACE}:{agent_type}") is False


def test_retired_mcp_prefix_is_not_classified_as_a_praxion_tool():
    """Canary: MCP tool names embed the plugin id, so they moved with it."""
    module = _load_hook("send_event")
    current = f"mcp__plugin_{CURRENT_NAMESPACE}_task-chronograph__get_pipeline_status"
    retired = f"mcp__plugin_{RETIRED_NAMESPACE}_task-chronograph__get_pipeline_status"
    assert module._classify_mcp_tool(current) == ("task-chronograph", "get_pipeline_status")
    assert module._classify_mcp_tool(retired) is None
