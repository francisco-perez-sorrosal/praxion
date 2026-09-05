"""Tests for scripts/spec_drift.py — pure detector entry point.

Verifies the three finding kinds (stale-dependent, orphaned-edge, untracked-req)
and the output contract shape for each, plus a false-positive guard for the
WIP-step sequencing suppression (load-bearing per the pre-mortem).

Imports are deferred into each test body so pytest collection succeeds before
scripts/spec_drift.py exists (required RED handshake in concurrent BDD/TDD mode).
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    assert isinstance(finding["rationale"], str), "rationale must be a non-empty string"
    assert finding["rationale"], "rationale must be a non-empty string"
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

    # Arrange: SPEC_DELTA adds a requirement that traceability.yml has no entry for.
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
        f"Expected at least one untracked-req finding for the requirement absent "
        f"from traceability.yml; "
        f"got: {findings!r}"
    )
    for finding in untracked:
        assert finding["severity"] == "important", (
            f"untracked-req must have severity=important; got {finding['severity']!r}"
        )
        _assert_finding_shape(finding, scope="in-flight:my-task")


# ---------------------------------------------------------------------------
# Test: suppressed-later-step — false-positive guard
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


# ---------------------------------------------------------------------------
# Test: the module loads, and reports, under an interpreter without PyYAML
# ---------------------------------------------------------------------------


def test_module_imports_without_pyyaml_present() -> None:
    """Importing this module must not require PyYAML.

    The sentinel invokes the spec-drift wrapper with a bare `python3`, which
    under a version manager's shim is routinely an interpreter holding none of
    the project's declared dependencies. A module-scope `import yaml` made the
    whole gate die on import — to pay for a dependency only the in-flight scope
    reaches, and the sentinel walks the archived one.
    """
    import ast

    source = (Path(__file__).parents[1] / "scripts" / "spec_drift.py").read_text(encoding="utf-8")
    module_level = [n for n in ast.parse(source).body if isinstance(n, ast.Import | ast.ImportFrom)]
    names = {
        a.name.split(".")[0] for n in module_level if isinstance(n, ast.Import) for a in n.names
    }
    names |= {(n.module or "").split(".")[0] for n in module_level if isinstance(n, ast.ImportFrom)}

    assert "yaml" not in names, "PyYAML must be imported on demand, never at module scope"


def test_missing_pyyaml_raises_rather_than_reporting_no_drift(tmp_path: Path, monkeypatch) -> None:
    """A detector that cannot read its input must not report a clean result.

    Returning `{}` here is indistinguishable from "this file declares no
    requirements", so the caller reports zero drift for a reason that has
    nothing to do with the code under test — green while not looking.
    """
    import pytest

    from scripts import spec_drift

    def _unavailable():
        raise RuntimeError("PyYAML is not importable under /usr/bin/python3")

    monkeypatch.setattr(spec_drift, "_require_yaml", _unavailable)
    traceability = tmp_path / "traceability.yml"
    traceability.write_text("requirements: {}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="PyYAML"):
        spec_drift._load_traceability(traceability)


# ---------------------------------------------------------------------------
# REQ_PATTERN corpus-form coverage (td-142: widen from bare-only to the live
# corpus's prefixed forms)
# ---------------------------------------------------------------------------

_SPECS_DIR = Path(__file__).parents[1] / ".ai-state" / "specs"


@pytest.mark.parametrize(
    "req_id",
    ["REQ-01", "REQ-PM-01", "REQ-DDL-01", "REQ-DIAGRAM-01"],  # id-citation-discipline:ignore
)
def test_req_pattern_matches_each_corpus_shape(req_id: str) -> None:
    """REQ_PATTERN matches bare and every prefixed form seen in .ai-state/specs/."""
    from scripts.spec_drift import REQ_PATTERN

    assert REQ_PATTERN.fullmatch(req_id), (
        f"REQ_PATTERN must match {req_id!r} — a shape present in the live spec corpus"
    )


def test_req_pattern_rejects_non_req_identifier_lookalikes() -> None:
    """REQ_PATTERN must not match prose words that merely start with 'REQ-'.

    The live corpus contains glossary prose like 'REQ-level' and 'REQ-tagged'
    that are not requirement identifiers — a pattern widened too far would
    misclassify them as untracked reqs.
    """
    from scripts.spec_drift import REQ_PATTERN

    for lookalike in (
        "REQ-level",  # id-citation-discipline:ignore
        "REQ-tagged",  # id-citation-discipline:ignore
        "REQ-ID",  # id-citation-discipline:ignore
        "REQ-DDLs",  # id-citation-discipline:ignore
    ):
        assert not REQ_PATTERN.fullmatch(lookalike), (
            f"REQ_PATTERN must not fullmatch prose lookalike {lookalike!r}"
        )


@pytest.mark.skipif(not _SPECS_DIR.is_dir(), reason="no .ai-state/specs/ corpus in this checkout")
def test_req_pattern_prefix_shapes_cover_the_live_corpus() -> None:
    """Canary: every REQ prefix token present in .ai-state/specs/ is matched.

    Parses the real corpus (not a fixture) for anything shaped like a REQ
    identifier and asserts REQ_PATTERN's matched set includes every distinct
    prefix token found — so a future corpus form (e.g. REQ-FOO-NN) that the  # id-citation-discipline:ignore
    pattern can't see fails this canary instead of silently going untracked.
    """
    import re as _re

    from scripts.spec_drift import REQ_PATTERN

    # Broad probe: anything "REQ-" followed by letters/digits/hyphens, so this
    # canary can detect a shape REQ_PATTERN itself would miss.
    probe = _re.compile(r"\bREQ-[A-Za-z0-9-]+\b")

    found_prefixes: set[str] = set()
    matched_prefixes: set[str] = set()
    for spec_file in _SPECS_DIR.glob("**/*.md"):
        content = spec_file.read_text(encoding="utf-8", errors="ignore")
        for candidate in probe.findall(content):
            # Only consider candidates that are genuine "REQ-<prefix>-NN" or
            # "REQ-NN" identifiers — i.e. end in digits — to exclude prose  # id-citation-discipline:ignore
            # lookalikes like "REQ-level" from the expected set.
            if not candidate[-1].isdigit():
                continue
            prefix_match = _re.fullmatch(r"REQ-(?:([A-Za-z]+)-)?\d+", candidate)
            if prefix_match is None:
                continue
            found_prefixes.add(prefix_match.group(1) or "")
            if REQ_PATTERN.fullmatch(candidate):
                matched_prefixes.add(prefix_match.group(1) or "")

    assert found_prefixes, "expected at least one REQ identifier in the live corpus"
    assert matched_prefixes == found_prefixes, (
        f"REQ_PATTERN misses corpus prefix shape(s): {found_prefixes - matched_prefixes!r}"
    )
