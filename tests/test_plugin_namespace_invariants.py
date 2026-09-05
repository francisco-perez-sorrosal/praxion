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

Historical records are deliberately exempt: under ``.ai-state/``, the
release ``CHANGELOG.md`` (generated from past commit messages, one entry per
past release), and the frozen reports under ``docs/independent-analysis/``
(the same carve-out the ADR-finalize walk scope grants them). An ADR, a
changelog entry, or an archived report naming the old identifier remains true
as a record of what was so when it was written; rewriting history to match
the present is what the frozen-artifact conventions forbid.

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
    "claude/aac-templates/precommit-block-d.sh.frag": (
        "shipped Block D template must resolve PLUGIN_ROOT via the pre-rename "
        "plugin-cache key too, or an already-onboarded project's golden-rule "
        "gate silently stops finding the plugin (td-145)"
    ),
    "scripts/assets/praxion-precommit-hook.sh.tmpl": (
        "shipped commit-gate template must resolve PLUGIN_ROOT via the "
        "pre-rename plugin-cache key too, for the same reason as the Block D "
        "template above (td-145)"
    ),
    "scripts/upgrade_project_pins.sh": (
        "must recognize a pre-rename plugin-cache merge-driver path as "
        "Praxion-managed, or every pre-rename project's driver registration "
        "is permanently reported as stale (td-145)"
    ),
    "scripts/test_upgrade_project_pins.py": (
        "fixture input driving the two reconciliation behaviors above: a "
        "workflow file still naming the retired agent prefix, and a merge "
        "driver still pointing at the retired plugin-cache path"
    ),
    "scripts/test_reconcile_aac_surfaces.py": (
        "fixture input for the installed-workflow namespace-drift detection "
        "the reconciler must repair"
    ),
}

# Generated projections of other files. They cannot be independently wrong: their
# text is copied from sources that are themselves exempt (an ADR title naming both
# the old and new identifier is correct, and regenerating preserves it). Editing
# one by hand to satisfy this scan would desynchronise it from its builder.
DERIVED_INDEXES: tuple[str, ...] = (".ai-state/doc_manifest.yaml",)

# Records of what was true when written. See the module docstring. Prefixes
# match subtrees; "CHANGELOG.md" is a full-path match against a single file
# (str.startswith accepts an exact-length prefix as well as a directory one).
HISTORICAL_PATHS: tuple[str, ...] = (
    ".ai-state/decisions/",
    ".ai-state/observations.jsonl",
    ".ai-state/TECH_DEBT_RESOLVED.md",
    ".ai-state/sentinel_reports/",
    ".ai-state/skill_genesis_reports/",
    ".ai-state/praxion_eval_reports/",
    ".ai-state/specs/",
    ".ai-state/calibration_log.md",
    "CHANGELOG.md",
    "docs/independent-analysis/",
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


# Directory names to skip during the no-``.git`` fallback walk (see
# ``_tracked_files``). ``.claude/worktrees`` is matched as a path prefix, not a
# bare name, because ``.claude/`` itself holds legitimately tracked files
# (``.claude/settings.json`` and friends) that a bare-name skip would drop.
_WALK_EXCLUDED_NAMES = frozenset({".git", "node_modules", "tmp"})
_WALK_EXCLUDED_PREFIX = (".claude", "worktrees")


def _tracked_files() -> list[str]:
    """Enumerate every file this scan should consider.

    ``git ls-files`` is authoritative in a real checkout -- including a
    worktree, where ``.git`` is a *file* pointing at the real gitdir, hence
    the ``exists()`` check rather than ``is_dir()``. But a clean extraction
    (``git archive`` output, e.g. from CI or the parity check this module's
    own docstring describes) has no ``.git`` at all, and a naive subprocess
    call from such a directory does not fail -- git walks upward, silently
    resolves to whichever *enclosing* repository happens to contain the
    extraction, and scopes the query to that subtree instead. Detect the
    missing ``.git`` and fall back to a plain filesystem walk so the verdict
    does not depend on where the extraction happens to sit.
    """
    if (REPO_ROOT / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in result.stdout.splitlines() if line]

    tracked: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if path.is_dir():
            continue
        parts = path.relative_to(REPO_ROOT).parts
        if _WALK_EXCLUDED_NAMES & set(parts):
            continue
        if parts[: len(_WALK_EXCLUDED_PREFIX)] == _WALK_EXCLUDED_PREFIX:
            continue
        tracked.append("/".join(parts))
    return tracked


def _is_historical(path: str) -> bool:
    return path.startswith(HISTORICAL_PATHS)


def test_manifest_declares_the_current_namespace():
    manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == CURRENT_NAMESPACE


def test_no_live_surface_carries_the_retired_namespace():
    offenders: list[str] = []
    for rel in _tracked_files():
        if _is_historical(rel) or rel in MIGRATION_REFERENCES or rel in DERIVED_INDEXES:
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


def test_upgrade_project_reconciles_the_instantiated_aac_templates():
    """td-145: a rename moves the *shipped* templates, but two of their
    renders are already instantiated into a managed project's own tree --
    `.github/workflows/architecture.yml` and the installed Block D
    pre-commit fragment -- and nothing else re-renders an existing copy.
    Both fail open if left stale: the workflow still reports green with the
    architecture sweep never running, and the golden-rule gate's skip notice
    misnames the plugin.

    `commands/upgrade-project.md` is a thin wrapper (as of the refactor that
    followed td-145's original fix) that delegates all reconciliation to
    `scripts/reconcile_aac_surfaces.py`; the drift-detection anchors --
    the two target paths and the two namespace-token regexes -- live in that
    script now, not in the command doc. This canary pins the delegation
    itself plus those anchors: if a future edit drops the delegation or
    either anchor, `/upgrade-project` silently stops detecting the drift and
    td-145 reopens with no test failing to say so.
    """
    wrapper = (REPO_ROOT / "commands" / "upgrade-project.md").read_text(encoding="utf-8")
    assert "scripts/reconcile_aac_surfaces.py" in wrapper

    reconciler = (REPO_ROOT / "scripts" / "reconcile_aac_surfaces.py").read_text(encoding="utf-8")
    assert ".github/workflows/architecture.yml" in reconciler
    assert ".git/hooks/pre-commit" in reconciler
    assert "architect-validator agent" in reconciler
    assert "plugin not found in installed_plugins" in reconciler


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
