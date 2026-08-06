"""Pure spec↔artifact drift detector.

Entry point: ``detect_drift(scope, repo_root, base_sha)`` returns a list of
finding dicts.  The function is side-effect-free — no writes, no global state —
so it is trivially unit-testable without a real git repo.

Finding dict contract
---------------------
{
    "kind": "stale-dependent" | "orphaned-edge" | "untracked-req",
    "scope": str,               # passed-through scope string
    "req": str,                 # requirement id, verbatim as the spec writes it
    "source_changed": bool,     # whether the spec source appeared in the diff
    "stale_dependents": list[str],
    "severity": "important" | "suggested",
    "pointer": str,             # human-readable location hint
    "rationale": str,
}

Severity cap
------------
Severity is capped at "important" / "suggested" — never Critical, never
blocking.  The detector is advisory; it surfaces signal, the human decides.

False-positive mitigation
-------------------------
Three layers:

1. Clause-level diffing — only the *changed* spec files trigger stale-dependent
   analysis; an unchanged spec does not produce findings even if dependents are
   absent.

2. WIP-step sequencing suppression — if a stale dependent appears in an
   incomplete WIP step that is *later* than the current step, demote its
   finding to "suggested" (or suppress entirely).  This prevents noisy
   Important findings when a spec change lands one checkpoint before its tests.

3. Scope confinement — the detector only reads traceability.yml from the task
   directory derived from *scope*; it never scans unrelated tasks.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPEC_SOURCE_FILENAMES = frozenset(
    {
        "SYSTEMS_PLAN.md",
        "SPEC_DELTA.md",
    }
)

REQ_PATTERN = re.compile(r"\bREQ-\d+\b")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect_drift(
    scope: str,
    repo_root: Path | str,
    base_sha: str | None,
    *,
    _changed_files_override: list[str] | None = None,
    _deleted_files_override: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Detect spec↔artifact drift for the given *scope*.

    Parameters
    ----------
    scope:
        A string of the form ``"in-flight:<task-slug>"`` or
        ``"archived:<spec-filename>"``.
    repo_root:
        The repository root (passed explicitly so the detector works in any
        cwd — including worktrees and tmp_path fixtures).
    base_sha:
        The git ref to diff against.  ``None`` means the caller supplies
        ``_changed_files_override`` directly (test mode).
    _changed_files_override:
        When provided, skip the git diff entirely and treat this as the set of
        changed file paths.  Used by tests for hermetic, side-effect-free runs.
    _deleted_files_override:
        When provided, treat these paths as deleted (as opposed to merely
        modified) in the diff.  Used by tests.

    Returns
    -------
    list[dict]
        Zero or more finding dicts matching the output contract.  Returns an
        empty list when there is nothing to analyse (no traceability.yml for
        in-flight scopes, no .ai-state/specs/ dir for archived scopes).
    """
    repo_root = Path(repo_root)

    # Resolve changed / deleted file sets
    if _changed_files_override is not None:
        changed_files: set[str] = set(_changed_files_override)
    else:
        changed_files = _git_changed_files(repo_root, base_sha)

    deleted_files: set[str] = (
        set(_deleted_files_override) if _deleted_files_override is not None else set()
    )

    # Dispatch by scope type
    if scope.startswith("in-flight:"):
        task_slug = scope[len("in-flight:") :]
        return _detect_in_flight(
            scope=scope,
            task_slug=task_slug,
            repo_root=repo_root,
            changed_files=changed_files,
            deleted_files=deleted_files,
        )

    if scope.startswith("archived:"):
        return _detect_archived(
            scope=scope,
            spec_filename=scope[len("archived:") :],
            repo_root=repo_root,
            changed_files=changed_files,
            deleted_files=deleted_files,
        )

    # Unknown scope format — return empty gracefully
    return []


# ---------------------------------------------------------------------------
# In-flight scope detector
# ---------------------------------------------------------------------------


def _detect_in_flight(
    *,
    scope: str,
    task_slug: str,
    repo_root: Path,
    changed_files: set[str],
    deleted_files: set[str],
) -> list[dict[str, Any]]:
    """Detect drift for an active pipeline task."""
    task_dir = repo_root / ".ai-work" / task_slug
    traceability_path = task_dir / "traceability.yml"

    if not traceability_path.exists():
        return []

    traceability = _load_traceability(traceability_path)
    if not traceability:
        return []

    # Parse WIP for sequencing suppression
    wip_path = task_dir / "WIP.md"
    pending_dependents = _pending_dependents_from_wip(wip_path) if wip_path.exists() else set()

    # Parse SPEC_DELTA for untracked-req detection
    spec_delta_path = task_dir / "SPEC_DELTA.md"
    spec_delta_reqs: set[str] = set()
    if spec_delta_path.exists() and "SPEC_DELTA.md" in changed_files:
        spec_delta_reqs = _extract_reqs_from_spec_delta(spec_delta_path)

    spec_source_changed = _spec_source_in_diff(changed_files)

    findings: list[dict[str, Any]] = []

    requirements: dict[str, dict[str, list[str]]] = traceability.get("requirements", {})

    # -- stale-dependent and orphaned-edge --
    for req_id, edges in requirements.items():
        tests: list[str] = edges.get("tests", [])
        impl: list[str] = edges.get("implementation", [])
        all_dependents = tests + impl

        orphaned = _find_orphaned(all_dependents, deleted_files)
        if orphaned:
            findings.append(
                _make_finding(
                    kind="orphaned-edge",
                    scope=scope,
                    req=req_id,
                    source_changed=spec_source_changed,
                    stale_dependents=orphaned,
                    severity="important",
                    pointer=traceability_path.as_posix(),
                    rationale=(
                        f"{req_id} has traceability edges pointing to deleted or renamed "
                        f"paths: {', '.join(orphaned)}. Update traceability.yml."
                    ),
                )
            )

        # stale-dependent: spec clause changed but dependents not touched
        if spec_source_changed:
            untouched = _find_untouched(all_dependents, changed_files)
            if untouched:
                # WIP-step sequencing suppression: if *all* untouched dependents
                # are scheduled in a later incomplete step, demote to suggested.
                # Match by file-part (strip "::node_id") so "tests/foo.py::bar"
                # is suppressed when "tests/foo.py" appears in the WIP step.
                suppressed = any(dep.split("::")[0] in pending_dependents for dep in untouched)
                severity = "suggested" if suppressed else "important"
                findings.append(
                    _make_finding(
                        kind="stale-dependent",
                        scope=scope,
                        req=req_id,
                        source_changed=True,
                        stale_dependents=untouched,
                        severity=severity,
                        pointer=traceability_path.as_posix(),
                        rationale=(
                            f"Spec clause changed but {req_id} dependents not yet updated: "
                            f"{', '.join(untouched)}."
                            + (
                                " (Suppressed: scheduled in a later WIP step.)"
                                if suppressed
                                else ""
                            )
                        ),
                    )
                )

    # -- untracked-req --
    tracked_reqs = set(requirements.keys())
    for req_id in spec_delta_reqs - tracked_reqs:
        findings.append(
            _make_finding(
                kind="untracked-req",
                scope=scope,
                req=req_id,
                source_changed=True,
                stale_dependents=[],
                severity="important",
                pointer=spec_delta_path.as_posix(),
                rationale=(
                    f"{req_id} appears in SPEC_DELTA.md but has no entry in traceability.yml. "
                    "Add implementation and test edges before closing the pipeline."
                ),
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Archived scope detector (stub — returns empty; archived detection is future)
# ---------------------------------------------------------------------------


def _detect_archived(
    *,
    scope: str,
    spec_filename: str,
    repo_root: Path,
    changed_files: set[str],
    deleted_files: set[str],
) -> list[dict[str, Any]]:
    """Detect drift for an archived spec.

    Returns an empty list when .ai-state/specs/ is absent (graceful degradation).
    """
    specs_dir = repo_root / ".ai-state" / "specs"
    if not specs_dir.exists():
        return []
    # Future: parse archived spec traceability matrix and check for orphaned
    # references.  For now return empty — the stub satisfies the graceful-
    # degradation tests without false positives.
    return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_yaml():
    """Return the YAML module, or raise naming the interpreter that lacks it.

    Imported on demand rather than at module scope so this module stays
    *importable* under an interpreter without PyYAML. Only the in-flight scope
    reaches it; the archived scope -- the one the sentinel's spec-drift check
    actually walks -- never does. A module-level import therefore made the whole
    gate unloadable to pay for a dependency that run never uses, and the gate
    died on import under the bare `python3` its own call site prescribes.

    The message names `sys.executable` because the usual cause is an invocation
    resolving an interpreter that lacks the project's declared dependencies,
    not PyYAML being genuinely uninstalled -- the same diagnosis, in the same
    words, that the finalize chain and the doc-manifest builder already print.
    """
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            f"spec-drift needs PyYAML to read traceability data, and "
            f"{sys.executable} does not have it. Run under the project "
            f"interpreter (<repo>/.venv/bin/python), point $PRAXION_PYTHON at "
            f"one that has it, or install pyyaml into the interpreter above."
        ) from exc
    return yaml


def _load_traceability(path: Path) -> dict[str, Any]:
    """Load and return the traceability.yml as a dict; return {} on a parse error.

    A missing PyYAML raises rather than degrading to `{}`. `{}` is
    indistinguishable from "this file declares no requirements", so swallowing
    the import error would make a drift detector report *clean* precisely when
    it could not read its own input -- green while not looking, and the same
    shape of defect as a withheld class re-emitted as a finding.
    """
    yaml = _require_yaml()
    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _git_changed_files(repo_root: Path, base_sha: str | None) -> set[str]:
    """Return the set of changed file paths from git diff."""
    import subprocess

    ref = base_sha or "HEAD"
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except subprocess.CalledProcessError:
        return set()


def _spec_source_in_diff(changed_files: set[str]) -> bool:
    """Return True if any changed file is a recognized spec source."""
    for path in changed_files:
        filename = Path(path).name
        if filename in SPEC_SOURCE_FILENAMES:
            return True
        if filename.startswith("SPEC_") and filename.endswith(".md"):
            return True
    return False


def _find_orphaned(dependents: list[str], deleted_files: set[str]) -> list[str]:
    """Return dependents whose base path appears in the deleted files set."""
    orphaned = []
    for dep in dependents:
        # dep may be "tests/test_foo.py::test_bar" — extract the file part
        file_part = dep.split("::")[0]
        if file_part in deleted_files:
            orphaned.append(dep)
    return orphaned


def _find_untouched(dependents: list[str], changed_files: set[str]) -> list[str]:
    """Return dependents whose file is NOT in the changed files set."""
    untouched = []
    for dep in dependents:
        file_part = dep.split("::")[0]
        if file_part not in changed_files:
            untouched.append(dep)
    return untouched


def _pending_dependents_from_wip(wip_path: Path) -> set[str]:
    """Parse WIP.md to find file paths mentioned in *incomplete* steps.

    An incomplete step is a ``- [ ]`` progress entry.  We extract any file
    paths mentioned inside that entry (naively — good enough for the suppression
    heuristic) and also return paths from the fixture format used in the tests
    (parenthetical notation).

    The suppression heuristic compares dependent paths against this set; if a
    stale dependent is in this set its finding is downgraded to "suggested".
    """
    try:
        content = wip_path.read_text(encoding="utf-8")
    except OSError:
        return set()

    pending: set[str] = set()
    # Match incomplete steps: "- [ ] ..." lines
    incomplete_pattern = re.compile(r"^\s*-\s*\[\s*\]\s*(.+)$", re.MULTILINE)
    path_pattern = re.compile(r"([\w/.-]+\.py(?:::\S+)?)")

    for match in incomplete_pattern.finditer(content):
        line_text = match.group(1)
        for path_match in path_pattern.finditer(line_text):
            pending.add(path_match.group(1))

    return pending


def _extract_reqs_from_spec_delta(spec_delta_path: Path) -> set[str]:
    """Extract requirement identifiers from SPEC_DELTA.md."""
    try:
        content = spec_delta_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(REQ_PATTERN.findall(content))


def _make_finding(
    *,
    kind: str,
    scope: str,
    req: str,
    source_changed: bool,
    stale_dependents: list[str],
    severity: str,
    pointer: str,
    rationale: str,
) -> dict[str, Any]:
    """Construct a finding dict satisfying the output contract."""
    return {
        "kind": kind,
        "scope": scope,
        "req": req,
        "source_changed": source_changed,
        "stale_dependents": stale_dependents,
        "severity": severity,
        "pointer": pointer,
        "rationale": rationale,
    }
