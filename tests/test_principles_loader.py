"""Tests for scripts/principles_loader.py — tolerant YAML loader for per-project principles.

Assumed public API (Step 3's implementer must satisfy this contract):

    load_principles(principles_yaml_path: Path) -> list[dict]
        Reads .ai-state/principles.yaml tolerantly.
        - Absent file  → returns []  (no raise)
        - Empty file   → returns []  (no raise)
        - Malformed YAML → returns [] (no raise); the returned list may additionally
          contain one dict with kind="malformed-yaml" so callers can log it, but the
          calling code must NOT break if that note-dict is absent.
        - Valid file   → returns a list of principle dicts normalized as follows:
            {
                "id": str,
                "statement": str,
                "severity": "advisory" | "blocking",  # always one of these two
                "scope": str | list[str],              # default "*" when absent
                "rationale": str | None,
                "_coerced_severity": bool,             # True if original value was unknown
            }

    scope_matches(scope: str | list[str], changed_files: list[str]) -> bool
        fnmatch-based applicability check.
        scope="*" matches everything.
        A list of globs: True if any glob matches any file.

Imports are deferred into each test body so pytest collection succeeds before
scripts/principles_loader.py exists (required RED handshake in concurrent BDD/TDD mode).
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "principles"

# ---------------------------------------------------------------------------
# Output-contract shape helpers
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = {"advisory", "blocking"}


def _assert_principle_shape(p: dict) -> None:
    """Assert a principle dict satisfies the normalized output contract."""
    assert "id" in p, f"Principle missing 'id' key: {p!r}"
    assert "statement" in p, f"Principle missing 'statement' key: {p!r}"
    assert "severity" in p, f"Principle missing 'severity' key: {p!r}"
    assert p["severity"] in _VALID_SEVERITIES, (
        f"severity must be one of {_VALID_SEVERITIES!r}, got {p['severity']!r}"
    )
    assert "scope" in p, f"Principle missing 'scope' key: {p!r}"
    assert "rationale" in p, f"Principle missing 'rationale' key: {p!r}"
    assert "_coerced_severity" in p, f"Principle missing '_coerced_severity' key: {p!r}"
    assert isinstance(p["_coerced_severity"], bool), (
        f"_coerced_severity must be bool, got {type(p['_coerced_severity'])!r}"
    )
    assert isinstance(p["id"], str), "id must be a non-empty string"
    assert p["id"], "id must be a non-empty string"
    assert isinstance(p["statement"], str), "statement must be a non-empty string"
    assert p["statement"], "statement must be a non-empty string"


# ---------------------------------------------------------------------------
# Scenario 1: valid file → parsed list with correct types
# ---------------------------------------------------------------------------


def test_valid_principles_file_returns_list_of_principle_dicts() -> None:
    """A valid principles YAML returns a list of dicts with all required normalized fields."""
    from scripts.principles_loader import load_principles  # deferred import for RED handshake

    fixture = FIXTURES / "valid_principles.yaml"
    principles = load_principles(fixture)

    # Two principles in the fixture
    assert len(principles) == 2, f"Expected 2 principles, got {len(principles)}: {principles!r}"

    for p in principles:
        _assert_principle_shape(p)

    # Verify specific principle content
    blocking = next((p for p in principles if p["id"] == "no-raw-sql"), None)
    assert blocking is not None, "Expected principle with id='no-raw-sql'"
    assert blocking["severity"] == "blocking"
    assert blocking["scope"] == "src/api/**"
    assert blocking["rationale"] is not None
    assert "query auditing" in blocking["rationale"]
    assert blocking["_coerced_severity"] is False

    advisory = next((p for p in principles if p["id"] == "public-fn-docstrings"), None)
    assert advisory is not None, "Expected principle with id='public-fn-docstrings'"
    assert advisory["severity"] == "advisory"
    assert advisory["scope"] == "*", f"Absent scope must default to '*', got {advisory['scope']!r}"
    assert advisory["rationale"] is None
    assert advisory["_coerced_severity"] is False


# ---------------------------------------------------------------------------
# Scenario 2: absent file → [] (no raise)
# ---------------------------------------------------------------------------


def test_absent_principles_file_returns_empty_list_without_raising(tmp_path: Path) -> None:
    """A path that does not exist returns [] — no exception raised."""
    from scripts.principles_loader import load_principles  # deferred import for RED handshake

    nonexistent = tmp_path / ".ai-state" / "principles.yaml"
    # Deliberately do not create the file

    principles = load_principles(nonexistent)

    assert principles == [], f"Expected [] for absent file, got {principles!r}"


# ---------------------------------------------------------------------------
# Scenario 3: empty file → [] (no raise)
# ---------------------------------------------------------------------------


def test_empty_principles_file_returns_empty_list_without_raising() -> None:
    """A principles YAML with an empty list returns [] — no exception raised."""
    from scripts.principles_loader import load_principles  # deferred import for RED handshake

    fixture = FIXTURES / "empty_principles.yaml"
    principles = load_principles(fixture)

    # Filter out any note-dicts (kind="malformed-yaml") — the empty list is the behavior under test
    real_principles = [p for p in principles if p.get("kind") != "malformed-yaml"]
    assert real_principles == [], (
        f"Expected [] (no real principles) for empty principles list, got {real_principles!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 4: malformed YAML → [] — THE LOAD-BEARING FAIL-SAFE TEST
#
# Pre-mortem risk: a user typo in principles.yaml must NEVER fail closed and
# break a pipeline run. The loader must swallow YAML parse errors and return
# an empty list (or a list containing only a note-dict with kind="malformed-yaml").
# ---------------------------------------------------------------------------


def test_malformed_yaml_returns_empty_list_without_raising() -> None:
    """Unparseable YAML returns [] and does NOT raise — fail-safe, never fail-closed."""
    from scripts.principles_loader import load_principles  # deferred import for RED handshake

    fixture = FIXTURES / "malformed.yaml"
    # The critical contract: must NOT raise any exception
    try:
        principles = load_principles(fixture)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"load_principles raised {type(exc).__name__} on malformed YAML — "
            f"this violates the fail-safe contract: {exc}"
        )

    # Filter out any note-dicts — only real principles must be absent
    real_principles = [p for p in principles if p.get("kind") != "malformed-yaml"]
    assert real_principles == [], (
        f"Malformed YAML must produce no real principles, got {real_principles!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 5: scope-match → principle applies to a matching path
# ---------------------------------------------------------------------------


def test_scope_matches_returns_true_for_path_matching_glob() -> None:
    """scope_matches returns True when a changed file matches the scope glob."""
    from scripts.principles_loader import scope_matches  # deferred import for RED handshake

    # "src/api/**" must match "src/api/handler.py"
    result = scope_matches("src/api/**", ["src/api/handler.py"])
    assert result is True, (
        f"scope_matches('src/api/**', ['src/api/handler.py']) should be True, got {result!r}"
    )


def test_scope_wildcard_matches_any_file() -> None:
    """scope_matches returns True for scope='*' regardless of path."""
    from scripts.principles_loader import scope_matches  # deferred import for RED handshake

    result = scope_matches("*", ["tests/test_foo.py"])
    assert result is True, (
        f"scope_matches('*', ...) must always be True (default scope), got {result!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 6: scope-miss → principle filtered out for non-matching path
# ---------------------------------------------------------------------------


def test_scope_matches_returns_false_for_path_not_matching_glob() -> None:
    """scope_matches returns False when no changed file matches the scope glob."""
    from scripts.principles_loader import scope_matches  # deferred import for RED handshake

    # "src/api/**" must NOT match "tests/test_foo.py"
    result = scope_matches("src/api/**", ["tests/test_foo.py"])
    assert result is False, (
        f"scope_matches('src/api/**', ['tests/test_foo.py']) should be False, got {result!r}"
    )


def test_scope_matches_empty_changed_files_returns_false() -> None:
    """scope_matches returns False when changed_files is empty."""
    from scripts.principles_loader import scope_matches  # deferred import for RED handshake

    result = scope_matches("src/api/**", [])
    assert result is False, f"scope_matches with no changed files should be False, got {result!r}"


# ---------------------------------------------------------------------------
# Scenario 7: unknown severity → coerced to "advisory" with _coerced_severity=True
#
# SYSTEMS_PLAN states: "Unknown value → treated as 'advisory' + one WARN that the
# value was coerced (fail-safe, never fail-closed on a typo)."
# The _coerced_severity flag carries the coercion signal.
# ---------------------------------------------------------------------------


def test_unknown_severity_coerced_to_advisory_with_coercion_flag() -> None:
    """An unknown severity value is coerced to 'advisory' and _coerced_severity is True."""
    from scripts.principles_loader import load_principles  # deferred import for RED handshake

    fixture = FIXTURES / "unknown_severity.yaml"
    principles = load_principles(fixture)

    real_principles = [p for p in principles if p.get("kind") != "malformed-yaml"]
    assert len(real_principles) == 1, f"Expected exactly 1 real principle, got {real_principles!r}"

    p = real_principles[0]
    assert p["id"] == "experimental-rule"
    assert p["severity"] == "advisory", (
        f"Unknown severity 'experimental' must be coerced to 'advisory', got {p['severity']!r}"
    )
    assert p["_coerced_severity"] is True, (
        f"_coerced_severity must be True when severity was coerced, got {p['_coerced_severity']!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 8: severity routing → blocking→FAIL-class / advisory→WARN-class
#
# The SYSTEMS_PLAN describes this routing in the verifier, but load_principles
# must preserve the severity field faithfully so routing can be applied downstream.
# We verify the loader contract: loaded severity values ARE the routing inputs.
# ---------------------------------------------------------------------------


def test_blocking_principle_has_severity_blocking_for_downstream_routing() -> None:
    """A 'blocking' principle preserves severity='blocking' for downstream FAIL routing."""
    from scripts.principles_loader import load_principles  # deferred import for RED handshake

    fixture = FIXTURES / "mixed_severity.yaml"
    principles = load_principles(fixture)

    real_principles = [p for p in principles if p.get("kind") != "malformed-yaml"]
    blocking = next((p for p in real_principles if p["id"] == "blocking-rule"), None)
    assert blocking is not None, "Expected principle with id='blocking-rule'"
    blocking_sev = blocking["severity"]
    assert blocking_sev == "blocking", (
        f"blocking-rule must have severity='blocking' for FAIL routing; got {blocking_sev!r}"
    )
    assert blocking["_coerced_severity"] is False


def test_advisory_principle_has_severity_advisory_for_downstream_routing() -> None:
    """An 'advisory' principle preserves severity='advisory' for downstream WARN routing."""
    from scripts.principles_loader import load_principles  # deferred import for RED handshake

    fixture = FIXTURES / "mixed_severity.yaml"
    principles = load_principles(fixture)

    real_principles = [p for p in principles if p.get("kind") != "malformed-yaml"]
    advisory = next((p for p in real_principles if p["id"] == "advisory-rule"), None)
    assert advisory is not None, "Expected principle with id='advisory-rule'"
    advisory_sev = advisory["severity"]
    assert advisory_sev == "advisory", (
        f"advisory-rule must have severity='advisory' for WARN routing; got {advisory_sev!r}"
    )
    assert advisory["_coerced_severity"] is False


# ---------------------------------------------------------------------------
# Additional contract tests: scope as list, absent scope defaults to "*"
# ---------------------------------------------------------------------------


def test_scope_matches_list_of_globs_matches_any() -> None:
    """scope_matches accepts a list of globs and returns True if any glob matches any file."""
    from scripts.principles_loader import scope_matches  # deferred import for RED handshake

    # One glob matches, one doesn't — should be True
    result = scope_matches(["src/api/**", "src/core/**"], ["src/api/handler.py"])
    assert result is True, (
        f"scope_matches with list of globs should be True if any matches; got {result!r}"
    )


def test_scope_matches_list_of_globs_all_miss_returns_false() -> None:
    """scope_matches returns False when none of a list of globs matches any changed file."""
    from scripts.principles_loader import scope_matches  # deferred import for RED handshake

    result = scope_matches(["src/api/**", "src/core/**"], ["tests/test_foo.py"])
    assert result is False, (
        f"scope_matches with list of globs all missing should be False; got {result!r}"
    )


def test_load_principles_absent_scope_defaults_to_wildcard(tmp_path: Path) -> None:
    """A principle with no scope field has scope normalized to '*' (matches everything)."""
    from scripts.principles_loader import load_principles, scope_matches  # noqa: F401

    # Write a minimal principle without a scope field
    yaml_file = tmp_path / "principles.yaml"
    yaml_file.write_text(
        "version: 1\n"
        "principles:\n"
        "  - id: no-scope-rule\n"
        "    statement: No scope means project-wide.\n"
        "    severity: advisory\n"
    )

    principles = load_principles(yaml_file)
    real_principles = [p for p in principles if p.get("kind") != "malformed-yaml"]

    assert len(real_principles) == 1
    p = real_principles[0]
    assert p["scope"] == "*", f"Absent scope must default to '*', got {p['scope']!r}"
    # And scope_matches("*", ...) must return True for any file
    from scripts.principles_loader import scope_matches as sm

    assert sm(p["scope"], ["any/file/path.py"]) is True
