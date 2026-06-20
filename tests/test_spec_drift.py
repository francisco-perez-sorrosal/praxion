"""Tests for scripts/spec_drift.py — pure detector entry point.

Verifies the three finding kinds (stale-dependent, orphaned-edge, untracked-req)
and the output contract shape for each, plus a false-positive guard for the
WIP-step sequencing suppression (load-bearing per the pre-mortem).

Imports are deferred into each test body so pytest collection succeeds before
scripts/spec_drift.py exists (required RED handshake in concurrent BDD/TDD mode).
"""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "spec_drift"

# ---------------------------------------------------------------------------
# Output-contract shape helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "kind",
    "scope",
    "req",
    "source_changed",
    "stale_dependents",
    "severity",
    "pointer",
    "rationale",
}
_VALID_KINDS = {"stale-dependent", "orphaned-edge", "untracked-req"}
_VALID_SEVERITIES = {"important", "suggested"}


def _assert_finding_shape(finding: dict, *, scope: str) -> None:
    """Assert that a finding dict satisfies the output contract."""
    missing = _REQUIRED_KEYS - finding.keys()
    assert not missing, f"Finding missing required keys: {missing!r}\nFinding: {finding!r}"
    assert finding["kind"] in _VALID_KINDS, (
        f"kind must be one of {_VALID_KINDS!r}, got {finding['kind']!r}"
    )
    assert finding["severity"] in _VALID_SEVERITIES, (
        f"severity must be one of {_VALID_SEVERITIES!r}, got {finding['severity']!r}"
    )
    assert finding["scope"] == scope, (
        f"scope mismatch: expected {scope!r}, got {finding['scope']!r}"
    )
    assert isinstance(finding["stale_dependents"], list), (
        f"stale_dependents must be a list, got {type(finding['stale_dependents'])!r}"
    )
    assert isinstance(finding["rationale"], str) and finding["rationale"], (
        "rationale must be a non-empty string"
    )
    assert isinstance(finding["pointer"], str), "pointer must be a string"


# ---------------------------------------------------------------------------
# Test: stale-dependent — real omission (important severity)
# ---------------------------------------------------------------------------


def test_stale_dependent_real_omission_emits_important_finding(tmp_path: Path) -> None:
    """A changed REQ clause with no dependent touched emits a stale-dependent/important finding."""
    from scripts.spec_drift import detect_drift  # deferred import for RED handshake

    # Arrange: task directory with traceability.yml; git diff shows SYSTEMS_PLAN.md changed,
    # none of the mapped tests/impl files changed.
    task_dir = tmp_path / ".ai-work" / "my-task"
    task_dir.mkdir(parents=True)
    traceability = FIXTURES / "traceability_real_omission.yml"
    (task_dir / "traceability.yml").write_text(traceability.read_text())

    # Simulate a diff where only the spec clause changed (no test/impl files touched).
    changed_files = ["SYSTEMS_PLAN.md"]

    # Act
    findings = detect_drift(
        scope="in-flight:my-task",
        repo_root=tmp_path,
        base_sha=None,
        _changed_files_override=changed_files,
    )

    # Assert
    assert findings, (
        "Expected at least one finding for a changed REQ clause with no touched dependents"
    )
    stale = [f for f in findings if f["kind"] == "stale-dependent"]
    assert stale, f"Expected at least one stale-dependent finding; got: {findings!r}"
    important_stale = [f for f in stale if f["severity"] == "important"]
    assert important_stale, (
        f"Expected stale-dependent with severity=important for a real omission; got: {stale!r}"
    )
    for finding in important_stale:
        _assert_finding_shape(finding, scope="in-flight:my-task")


# ---------------------------------------------------------------------------
# Test: stale-dependent — pure refactor (suggested severity or suppressed)
# ---------------------------------------------------------------------------


def test_stale_dependent_pure_refactor_does_not_emit_important(tmp_path: Path) -> None:
    """An impl file changed without a REQ clause change emits suggested (not important) or nothing."""
    from scripts.spec_drift import detect_drift  # deferred import for RED handshake

    # Arrange: only the impl file changed, not the spec clause for its REQ.
    task_dir = tmp_path / ".ai-work" / "my-task"
    task_dir.mkdir(parents=True)
    traceability = FIXTURES / "traceability_pure_refactor.yml"
    (task_dir / "traceability.yml").write_text(traceability.read_text())

    # Diff: impl changed, but REQ clause (in SYSTEMS_PLAN) not in the diff.
    changed_files = ["src/widget_render.py"]

    # Act
    findings = detect_drift(
        scope="in-flight:my-task",
        repo_root=tmp_path,
        base_sha=None,
        _changed_files_override=changed_files,
    )

    # Assert: no Important findings — pure refactor must not trigger Important.
    important_findings = [f for f in findings if f["severity"] == "important"]
    assert not important_findings, (
        f"Pure refactor (no REQ clause change) must not produce important findings; got: {important_findings!r}"
    )
    # Any findings that do exist must be suggested.
    for finding in findings:
        _assert_finding_shape(finding, scope="in-flight:my-task")


# ---------------------------------------------------------------------------
# Test: orphaned-edge (deleted target path)
# ---------------------------------------------------------------------------


def test_orphaned_edge_emits_important_finding(tmp_path: Path) -> None:
    """A traceability edge pointing to a deleted/renamed file emits orphaned-edge/important."""
    from scripts.spec_drift import detect_drift  # deferred import for RED handshake

    # Arrange: traceability.yml has edges to files that appear as deleted in the diff.
    task_dir = tmp_path / ".ai-work" / "my-task"
    task_dir.mkdir(parents=True)
    traceability = FIXTURES / "traceability_orphaned_edge.yml"
    (task_dir / "traceability.yml").write_text(traceability.read_text())

    # Simulate a diff where the mapped test file was deleted.
    changed_files = ["tests/test_deleted_module.py", "src/old_module.py"]
    deleted_files = ["tests/test_deleted_module.py", "src/old_module.py"]

    # Act
    findings = detect_drift(
        scope="in-flight:my-task",
        repo_root=tmp_path,
        base_sha=None,
        _changed_files_override=changed_files,
        _deleted_files_override=deleted_files,
    )

    # Assert
    orphaned = [f for f in findings if f["kind"] == "orphaned-edge"]
    assert orphaned, f"Expected at least one orphaned-edge finding; got: {findings!r}"
    for finding in orphaned:
        assert finding["severity"] == "important", (
            f"orphaned-edge must have severity=important; got {finding['severity']!r}"
        )
        _assert_finding_shape(finding, scope="in-flight:my-task")


# ---------------------------------------------------------------------------
# Test: untracked-req (REQ in SPEC_DELTA, no traceability edge)
# ---------------------------------------------------------------------------


def test_untracked_req_emits_important_finding(tmp_path: Path) -> None:
    """A REQ added by SPEC_DELTA with no traceability edge emits untracked-req/important."""
    from scripts.spec_drift import detect_drift  # deferred import for RED handshake

    # Arrange: traceability.yml has no entry for REQ-04; SPEC_DELTA adds REQ-04.
    task_dir = tmp_path / ".ai-work" / "my-task"
    task_dir.mkdir(parents=True)
    traceability = FIXTURES / "traceability_untracked_req.yml"
    (task_dir / "traceability.yml").write_text(traceability.read_text())
    spec_delta = FIXTURES / "spec_delta_untracked_req.md"
    (task_dir / "SPEC_DELTA.md").write_text(spec_delta.read_text())

    changed_files = ["SPEC_DELTA.md"]

    # Act
    findings = detect_drift(
        scope="in-flight:my-task",
        repo_root=tmp_path,
        base_sha=None,
        _changed_files_override=changed_files,
    )

    # Assert
    untracked = [f for f in findings if f["kind"] == "untracked-req"]
    assert untracked, (
        f"Expected at least one untracked-req finding for REQ-04 absent from traceability.yml; "
        f"got: {findings!r}"
    )
    for finding in untracked:
        assert finding["severity"] == "important", (
            f"untracked-req must have severity=important; got {finding['severity']!r}"
        )
        _assert_finding_shape(finding, scope="in-flight:my-task")


# ---------------------------------------------------------------------------
# Test: suppressed-later-step — false-positive guard (AC-7)
# ---------------------------------------------------------------------------


def test_later_wip_step_dependents_produce_no_important_finding(tmp_path: Path) -> None:
    """Dependents scheduled in a not-yet-complete WIP step must not produce Important findings.

    This is the load-bearing false-positive guard: a spec edit lands one checkpoint
    before its tests, which are listed in an incomplete WIP step. The detector must
    suppress Important findings and produce at most Suggested or nothing.
    """
    from scripts.spec_drift import detect_drift  # deferred import for RED handshake

    # Arrange: SYSTEMS_PLAN changed (spec clause), tests in a future incomplete WIP step.
    task_dir = tmp_path / ".ai-work" / "my-task"
    task_dir.mkdir(parents=True)
    traceability = FIXTURES / "traceability_suppressed_later_step.yml"
    (task_dir / "traceability.yml").write_text(traceability.read_text())
    wip = FIXTURES / "wip_suppressed_later_step.md"
    (task_dir / "WIP.md").write_text(wip.read_text())

    # Spec clause changed; tests not touched (they're scheduled in step 3 = incomplete).
    changed_files = ["SYSTEMS_PLAN.md"]

    # Act
    findings = detect_drift(
        scope="in-flight:my-task",
        repo_root=tmp_path,
        base_sha=None,
        _changed_files_override=changed_files,
    )

    # Assert: zero Important findings — sequencing suppression must fire.
    important_findings = [f for f in findings if f["severity"] == "important"]
    assert not important_findings, (
        f"WIP-step sequencing suppression failed: got Important findings for a "
        f"dependent scheduled in an incomplete step: {important_findings!r}"
    )


# ---------------------------------------------------------------------------
# Test: no traceability.yml → empty list (graceful)
# ---------------------------------------------------------------------------


def test_no_traceability_yml_returns_empty_list(tmp_path: Path) -> None:
    """When the scope has no traceability.yml, detect_drift returns an empty list."""
    from scripts.spec_drift import detect_drift  # deferred import for RED handshake

    # Arrange: task dir with no traceability.yml at all.
    task_dir = tmp_path / ".ai-work" / "empty-task"
    task_dir.mkdir(parents=True)

    # Act
    findings = detect_drift(
        scope="in-flight:empty-task",
        repo_root=tmp_path,
        base_sha=None,
    )

    # Assert
    assert findings == [], f"Expected empty list when no traceability.yml exists; got: {findings!r}"


# ---------------------------------------------------------------------------
# Test: no .ai-state/specs/ dir → empty list (archived scope, graceful)
# ---------------------------------------------------------------------------


def test_no_specs_dir_returns_empty_list_for_archived_scope(tmp_path: Path) -> None:
    """When .ai-state/specs/ is absent, detect_drift for an archived scope returns []."""
    from scripts.spec_drift import detect_drift  # deferred import for RED handshake

    # Arrange: repo root with no .ai-state/specs/ directory.
    (tmp_path / ".ai-state").mkdir()
    # No specs/ subdirectory created.

    # Act
    findings = detect_drift(
        scope="archived:SPEC_my-feature_2026-06-19.md",
        repo_root=tmp_path,
        base_sha=None,
    )

    # Assert
    assert findings == [], f"Expected empty list when .ai-state/specs/ is absent; got: {findings!r}"
